"""Data-only entry point for the self-hosted Pyodide worker."""
import json
from .market import JointHistory, Observation
from .longevity import LifeTable
from .retirement import compare_retirement

BROWSER_MODEL_VERSION='retirement-plans-real-cny-v1'


def run_browser(payload_json, progress=None):
    payload=json.loads(payload_json)
    if payload.get('model_version')!=BROWSER_MODEL_VERSION:
        raise ValueError('计算规则已更新，请刷新页面后重新运行。')
    scenario=payload['scenario']
    if scenario['horizon'] not in ('rolling','fixed90'):
        raise ValueError('请选择滚动寿命或固定90岁。')
    source=payload['inputs']['source'];raw=source['history']
    history=JointHistory(tuple(Observation(**r) for r in raw['rows']),raw['kind'],raw['label'],tuple(raw['sources']),tuple(raw['limitations']))
    mortality=payload['inputs']['mortality']
    table=LifeTable(mortality['rows'],mortality['source'])
    result=compare_retirement(scenario,history,table,progress=progress)
    result.pop('paths',None);result.pop('path_metrics',None)
    reports=[result,*result['retirement_comparison']['cases'].values()]
    for report in reports:
        variants=[report,*report.get('horizon_comparison',{}).get('cases',{}).values()]
        for variant in variants:
            variant['provenance'].update(compute_location='browser',engine_sha256=payload['engine_sha256'],model_version=BROWSER_MODEL_VERSION,
                raw_source_sha256=source.get('audit',{}).get('files',{}),local_dataset_id=scenario['dataset'])
    return json.dumps(result,ensure_ascii=False,allow_nan=False)
