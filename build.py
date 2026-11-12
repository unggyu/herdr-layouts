"""Build the checked-out branch into a portable Windows installation ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent


def build(runtime_dir=None):
    profile=json.loads((ROOT/'profile.json').read_text(encoding='utf-8'))
    stage=ROOT/'build'/profile['artifact']
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name in ['install.py','install.cmd','README.md','NOTICE.md','LICENSE']:
        shutil.copy2(ROOT/name,stage/name)
    shutil.copy2(ROOT/'keys.patch.json',stage/'keys.patch.json')
    # Copy only version-controlled source folders, never local service state.
    shutil.copytree(ROOT/'payload',stage/'payload',ignore=shutil.ignore_patterns('data','__pycache__','*.pyc','*.backup-*','*.error','*.log'))
    runtime=stage/'runtime'
    if runtime_dir:
        shutil.copytree(runtime_dir,runtime)
    else:
        lock=json.loads((ROOT/'runtime.lock.json').read_text(encoding='utf-8'))
        archive=ROOT/'.cache'/Path(lock['url']).name
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            print('Downloading embedded Python '+lock['version'],flush=True)
            temporary=archive.with_suffix('.download')
            with urllib.request.urlopen(lock['url'],timeout=60) as response,temporary.open('wb') as output:
                shutil.copyfileobj(response,output)
            temporary.replace(archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=lock['sha256']:
            raise RuntimeError('Embedded Python checksum mismatch: '+str(archive))
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                path=Path(name)
                if path.is_absolute() or '..' in path.parts:raise RuntimeError('Unsafe runtime archive entry')
            bundle.extractall(runtime)
    hashes={file.relative_to(stage).as_posix():hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(stage.rglob('*')) if file.is_file()}
    manifest={'format':1,'layout':profile['layout'],'mods':profile['mods'],'sha256':hashes}
    (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    output=dist/(profile['artifact']+'.zip')
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for file in sorted(stage.rglob('*')):
            if file.is_file():bundle.write(file,str(file.relative_to(stage.parent)))
    output.with_suffix('.zip.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
    print('Built:',output)
    print('Layout:',profile['layout'],'Files:',len(hashes)+1,'ZIP bytes:',output.stat().st_size)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir',type=Path,help='Use an existing Windows embedded Python folder instead of downloading')
    build(parser.parse_args().runtime_dir)
