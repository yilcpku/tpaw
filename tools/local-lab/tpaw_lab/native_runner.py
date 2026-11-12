"""Run pinned native code in an isolated, time-limited local child process."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from .native_control import verified_config
from .storage import private_root


class NativeRunner:
    def __init__(self,config:Path,store):
        self.config=config.resolve(strict=True);verified_config(self.config)
        self.store=store

    def run(self,scenario:dict)->dict:
        selection=scenario.get('native_control',{})
        retirement=selection.get('retirement_month');horizon=selection.get('horizon')
        if not isinstance(retirement,str) or not isinstance(horizon,str):
            raise ValueError('请选择原生对照退休日与固定终点。')
        folder=private_root(self.store.root/'native-runs'/uuid.uuid4().hex)
        payload={'scenario':scenario,'retirement_month':retirement,'horizon':horizon}
        source=folder/'input.json'
        with source.open('x',encoding='utf-8') as handle:
            json.dump(payload,handle,ensure_ascii=False,allow_nan=False)
        worker=Path(__file__).resolve().parents[1]/'run_native_control.py'
        try:
            completed=subprocess.run([sys.executable,str(worker),'--config',str(self.config),
                '--input',str(source),'--output-dir',str(folder)],capture_output=True,timeout=300,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:
            raise ValueError('原生对照超出5分钟限制，子进程已停止；未返回部分结果。') from None
        if completed.returncode:
            raise ValueError('原生对照未完成或配对核验失败；未返回部分结果。请检查已固定的本地CUDA环境与输入范围。')
        result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        result['input_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        key=self.store.put('results',{'name':scenario['name']+' · 原生当前输入对照','scenario':scenario,'result':result})
        result['local_result_id']=key
        return result
