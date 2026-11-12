"""Loopback-only local UI/API. Personal records stay in a verified private root."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote, urlsplit
from tpaw_lab.longevity import LifeTable
from tpaw_lab.market import JointHistory, Observation
from tpaw_lab.simulation import compare_horizons
from tpaw_lab.comparison import compare_channels
from tpaw_lab.baseline import reference_view
from tpaw_lab.simulation import simulate
from tpaw_lab.storage import Store
from tpaw_lab.native_runner import NativeRunner
from tpaw_lab.data_audit import audit_view


FEATURES = [
    {"name":"滚动规划寿命 / 固定90岁对照", "state":"浏览器后台计算；100岁尾部单独保留"},
    {"name":"3个月不可逆通知期与候选退休日", "state":"已接入；尚待真实长路径全面回归"},
    {"name":"人民币存款、名义国债与独立现金底线", "state":"官方国债/中行挂牌历史2006–2025；变化同步抽样，合约单独记账"},
    {"name":"原版 TPAW", "state":"归档原生基准独立保留；1000条完整路径通过预设容差回归"},
    {"name":"2003年前全球股票代理", "state":"French代理、VWRL月度重叠和FTSE年度窗口差异已量化"},
    {"name":"1871–2026合成压力情景", "state":"已构造至2026年3月；与观测历史分开标注，待扩展验证"},
    {"name":"本地情景保存与载入", "state":"仅本地；写入前检查Git排除"},
    {"name":"阶段现金流与准备金", "state":"日期净储蓄/奖金、名义与实际费用、替换预算、退休时划分及严格等额支取"},
]


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, static,diagnostics_id=None,native_config=None):
        super().__init__(address, Handler)
        self.store, self.static = store, static.resolve()
        self.run_lock = threading.Lock()
        self.diagnostics_id=diagnostics_id
        self.native_runner=NativeRunner(native_config,store) if native_config else None


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def log_message(self, *_):
        pass  # Financial values and scenario names never enter HTTP logs.

    def headers_common(self,immutable=False):
        self.send_header("Cache-Control","public, max-age=31536000, immutable" if immutable else "no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

    def allowed(self, static=False):
        host = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get("Origin")
        # Public UI assets may be navigated to from another page or extension;
        # private API records and all writes still require the local origin.
        if static:
            return self.headers.get("Host")==host
        return (self.headers.get("Host")==host and (origin is None or origin=="http://"+host)
                and self.headers.get("Sec-Fetch-Site") not in ("cross-site","same-site"))

    def json(self, status, body):
        encoded = json.dumps(body,ensure_ascii=False,allow_nan=False).encode("utf-8")
        self.send_response(status);self.headers_common()
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(encoded)));self.end_headers();self.wfile.write(encoded)

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.allowed(static=not path.startswith("/api/")):
            self.json(403,{"error":"Local origin required"});return
        try:
            if path=="/api/status":
                datasets=[d for d in self.server.store.list("data") if d["id"]!="hk-male-period-2025"]
                self.json(200,{"engine":"TPAW portable research extension; native original retained separately",
                               "features":FEATURES,"datasets":datasets,"diagnostics_id":self.server.diagnostics_id,
                               "native_control_available":self.server.native_runner is not None});return
            if path=="/api/baselines":
                self.json(200,self.server.store.list("baselines"));return
            if path.startswith("/api/baselines/"):
                data=self.server.store.get("baselines",path.removeprefix("/api/baselines/"))
                self.json(200,{k:v for k,v in data.items() if k!='imported_scenario_inputs'});return
            if path=="/api/diagnostics" and self.server.diagnostics_id:
                data=self.server.store.get("results",self.server.diagnostics_id)
                view={k:data[k] for k in ('name','rate_sensitivities','limits')}
                for group in ('seed_sensitivities','regime_sensitivities'):
                    view[group]=[{k:v for k,v in row.items() if k in ('seed','regime','outcomes')}|{'cagr':row['moments']['global_cny_real']['compound_annual_growth_rate']} for row in data[group]]
                view['scenario_kind']='Generic verification example; not current inputs or personal finances'
                self.json(200,view);return
            if path=="/api/scenarios":
                self.json(200,self.server.store.list("scenarios"));return
            if path.startswith("/api/scenarios/"):
                self.json(200,self.server.store.get("scenarios",path.removeprefix("/api/scenarios/")));return
            if path.startswith("/api/data-audit/"):
                data=self.server.store.get("data",path.removeprefix("/api/data-audit/"))
                self.json(200,audit_view(data));return
            if path.startswith('/api/browser-inputs/'):
                source=self.server.store.get('data',path.removeprefix('/api/browser-inputs/'))
                self.json(200,{'source':source,'mortality':self.server.store.get('data','hk-male-period-2025')});return
            relative=unquote(path).lstrip("/") or "index.html"
            file=(self.server.static/relative).resolve()
            if not file.is_relative_to(self.server.static) or not file.is_file():
                self.json(404,{"error":"Local file not found"});return
            body=file.read_bytes()
            self.send_response(200);self.headers_common(immutable=relative.startswith('runtime/pyodide/') or (relative.startswith('runtime/engine-') and relative.endswith('.zip')))
            content_type={'.mjs':'text/javascript','.js':'text/javascript','.wasm':'application/wasm'}.get(file.suffix)
            self.send_header("Content-Type",content_type or mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        except (FileNotFoundError,ValueError):
            self.json(404,{"error":"Local record not found"})

    def do_POST(self):
        if not self.allowed() or self.headers.get("Content-Type","").split(";")[0]!="application/json":
            self.json(403,{"error":"Local JSON requests only"});return
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=2*1024*1024:
                self.json(413,{"error":"Request too large or empty"});return
            scenario=json.loads(self.rfile.read(length))
            if not isinstance(scenario,dict) or not isinstance(scenario.get("name"),str) or not scenario["name"].strip():
                raise ValueError("请填写情景名称。")
            path=urlsplit(self.path).path
            if path=='/api/results':
                # Persist a browser-computed report; never execute submitted code.
                result=scenario.get('result');inputs=scenario.get('scenario')
                if not isinstance(result,dict) or not isinstance(inputs,dict) or not isinstance(result.get('profiles'),list) or not isinstance(result.get('provenance'),dict):
                    raise ValueError('浏览器结果格式无效。')
                result.pop('paths',None);result.pop('path_metrics',None)
                result['provenance']['compute_location']='browser'
                if inputs.get('native_baseline_id'):
                    result['native_baseline']=reference_view(inputs,self.server.store.get('baselines',inputs['native_baseline_id']))
                key=self.server.store.put('results',{'name':scenario['name'],'scenario':inputs,'result':result})
                self.json(201,{'id':key,'native_baseline':result.get('native_baseline')});return
            if path=="/api/scenarios":
                key=self.server.store.put("scenarios",scenario)
                self.json(201,{"id":key});return
            if path not in ("/api/run","/api/run-native"):
                self.json(404,{"error":"Unknown local action"});return
            if not self.server.run_lock.acquire(blocking=False):
                self.json(409,{"error":"另一个本地模拟正在运行。"});return
            try:
                if path=="/api/run-native":
                    if not self.server.native_runner:raise ValueError('启动服务时尚未配置经过哈希固定的本地原生引擎。')
                    self.json(200,self.server.native_runner.run(scenario));return
                if not scenario.get("dataset"):
                    raise ValueError("请选择已核验的历史数据。")
                source=self.server.store.get("data",scenario["dataset"])
                raw=source["history"]
                history=JointHistory(tuple(Observation(**r) for r in raw["rows"]),raw["kind"],raw["label"],tuple(raw["sources"]),tuple(raw["limitations"]))
                mortality=self.server.store.get("data","hk-male-period-2025")
                table=LifeTable(mortality["rows"],mortality["source"])
                result=(compare_horizons if scenario.get('include_horizons',True) else simulate)(scenario,history,table)
                if scenario.get("include_attribution",False):
                    result["equity_channel_comparison"]=compare_channels(scenario,history,LifeTable(mortality["rows"],mortality["source"]))
                if scenario.get('native_baseline_id'):
                    baseline=self.server.store.get('baselines',scenario['native_baseline_id'])
                    result['native_baseline']=reference_view(scenario,baseline)
                result["provenance"]["raw_source_sha256"]=source.get("audit",{}).get("files",{})
                result["provenance"]["local_dataset_id"]=scenario["dataset"]
                key=self.server.store.put("results",{"name":scenario["name"],"scenario":scenario,"result":result})
                response={k:v for k,v in result.items() if k!="paths"}
                response["local_result_id"]=key
                self.json(200,response)
            finally:
                self.server.run_lock.release()
        except (ValueError,KeyError,TypeError,OverflowError,json.JSONDecodeError) as error:
            # Do not echo a serialized request or private values.
            self.json(400,{"error":str(error) if isinstance(error,ValueError) else "情景字段无效或不完整。"})
        except FileNotFoundError:
            self.json(400,{"error":"本地数据尚未准备；请先运行资料核验与准备命令。"})
        except Exception:
            self.json(500,{"error":"本地模拟未完成；没有返回部分结果。"})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,required=True)
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--diagnostics-id")
    parser.add_argument("--native-config",type=Path,help="Private JSON with pinned local DLL/source/table hashes and CUDA directory")
    a=parser.parse_args()
    static=Path(__file__).resolve().parents[2]/"packages"/"local-lab"/"dist"
    if not (static/"index.html").is_file():
        raise SystemExit("Build packages/local-lab first")
    server=LocalServer(("127.0.0.1",a.port),Store(a.data_dir),static,a.diagnostics_id,a.native_config)
    print(f"TPAW local research UI: http://127.0.0.1:{server.server_port}",flush=True)
    server.serve_forever()
