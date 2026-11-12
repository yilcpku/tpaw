"""Isolated local native worker; all inputs/outputs remain in private storage."""
import argparse
import json
from pathlib import Path
from tpaw_lab.native_control import verified_config,run_control
from tpaw_lab.storage import private_root

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    config=verified_config(a.config);payload=json.loads(a.input.read_text(encoding='utf-8'))
    folder=private_root(a.output_dir)
    result=run_control(payload['scenario'],payload['retirement_month'],payload['horizon'],config,folder)
    with (folder/'result.json').open('x',encoding='utf-8') as handle:
        json.dump(result,handle,ensure_ascii=False,allow_nan=False,indent=2)
