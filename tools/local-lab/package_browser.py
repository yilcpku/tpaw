"""Build a deterministic, public-code-only model archive and pinned local WASM assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

VERSION='314.0.7'
MODULES=('__init__','browser','market','longevity','simulation','comparison','policy','defensive','yields','cashflows','baseline')

def package(destination):
    root=Path(__file__).resolve().parent
    destination.mkdir(parents=True,exist_ok=True)
    archive=destination/'engine.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for module in MODULES:
            info=zipfile.ZipInfo(f'tpaw_lab/{module}.py',(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(root/'tpaw_lab'/f'{module}.py').read_bytes())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    named=destination/f'engine-{digest}.zip';archive.replace(named)
    (destination/'manifest.json').write_text(json.dumps({'archive':named.name,'sha256':digest,'pyodide':VERSION}),encoding='utf-8')
    source=root.parents[1]/'packages/local-lab/node_modules/pyodide'
    target=destination/'pyodide'/VERSION;target.mkdir(parents=True,exist_ok=True)
    for filename in ('pyodide.mjs','pyodide.asm.mjs','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json','README.md'):
        shutil.copyfile(source/filename,target/filename)
    shutil.copyfile(root.parents[1]/'LICENSE.md',destination/'TPAW-LICENSE.txt')
    print('Packaged public model',digest)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True)
    package(p.parse_args().destination)
