"""Data-only entry point for the self-hosted Pyodide worker."""
import json
from .market import JointHistory, Observation
from .longevity import LifeTable
from .simulation import compare_horizons


def run_browser(payload_json, progress=None):
    payload=json.loads(payload_json)
    scenario=payload['scenario']
    if scenario['horizon'] not in ('rolling','fixed90'):
        raise ValueError('请选择滚动寿命或固定90岁。')
    source=payload['inputs']['source'];raw=source['history']
    history=JointHistory(tuple(Observation(**r) for r in raw['rows']),raw['kind'],raw['label'],tuple(raw['sources']),tuple(raw['limitations']))
    mortality=payload['inputs']['mortality']
    table=LifeTable(mortality['rows'],mortality['source'])
    result=compare_horizons(scenario,history,table,modes=('rolling','fixed90'),retain_paths=False,progress=progress)
    result.pop('paths',None);result.pop('path_metrics',None)
    result['provenance'].update(compute_location='browser',engine_sha256=payload['engine_sha256'],
        raw_source_sha256=source.get('audit',{}).get('files',{}),local_dataset_id=scenario['dataset'])
    return json.dumps(result,ensure_ascii=False,allow_nan=False)
