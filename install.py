"""Install the exported Herdr customization into a Windows Herdr app home."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):stream.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent


def install(args):
    if os.name != 'nt':
        raise RuntimeError('This package targets Windows x64 + WSL. Run install.cmd on Windows.')
    app_home = Path(args.app_home or os.environ.get('HERDR_APP_HOME') or Path.home()/'.config/herdr-app')
    runtime = Path(args.runtime_dir or Path(os.environ['LOCALAPPDATA'])/'Programs/herdr-layout-python')
    app = Path(os.environ['LOCALAPPDATA'])/'Programs/herdr-app/herdr-app.exe'
    if not app.is_file():
        raise RuntimeError('Install Herdr for Windows and launch it once before importing this package.')
    # Check packaged payload before changing the destination.
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    layout_name = manifest['layout']
    for name, digest in manifest['sha256'].items():
        file = ROOT/name
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Package checksum mismatch: '+name)
    keys_path = app_home/'keys.json'
    keys = json.loads(keys_path.read_text(encoding='utf-8-sig')) if keys_path.exists() else {}
    patch = json.loads((ROOT/'keys.patch.json').read_text(encoding='utf-8'))
    for section, bindings in patch.items():
        if not isinstance(keys.get(section, {}), dict):
            raise RuntimeError('Invalid keys.json section: '+section)
        keys.setdefault(section, {}).update(bindings)
    backup = app_home/'backups'/(layout_name+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    def save_existing(path, relative):
        if path.is_file():
            copy = backup/relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copy)
    python = (runtime/'python.exe').as_posix()
    replacements = {'__HERDR_PYTHON__':python, '__WINDOWS_ROOT__':Path(os.environ['SystemRoot']).as_posix(),
                    '__RUNTIME_FOLDER__':runtime.name,
                    '__HERDR_PYTHONW_PS__':(runtime/'pythonw.exe').as_posix().replace("'", "''")}
    for source in (ROOT/'payload').rglob('*'):
        if not source.is_file(): continue
        relative = source.relative_to(ROOT/'payload')
        dest = app_home/relative
        save_existing(dest, relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in {'.js','.py','.ps1','.json'}:
            text = source.read_text(encoding='utf-8')
            for token, value in replacements.items():text = text.replace(token, value)
            dest.write_text(text, encoding='utf-8')
        else: shutil.copy2(source, dest)
    runtime.mkdir(parents=True, exist_ok=True)
    for source in (ROOT/'runtime').iterdir():
        if source.is_file(): shutil.copy2(source, runtime/source.name)
    save_existing(keys_path, Path('keys.json'))
    keys_path.write_text(json.dumps(keys, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    # A new computer starts with its own empty session registry, never this PC's chats.
    recovery = app_home/'mods/session-restore'
    original = recovery/'original-shell.json'
    core_config = Path(os.environ['APPDATA'])/'herdr-core/config.toml'
    contents = core_config.read_text(encoding='utf-8-sig') if core_config.exists() else ''
    core_settings = tomllib.loads(contents)
    if not original.exists():
        original.write_text(json.dumps(core_settings.get('shell') or ['powershell.exe','-NoLogo']), encoding='utf-8')
    if args.enable_session_recovery:
        desired = [str(runtime/'python.exe'),'-I',str(recovery/'restore.py'),'--shell']
        existing = core_settings.get('shell')
        if existing and existing != desired:
            print('Existing core shell preserved. Automatic shell recovery was not enabled; see README.')
        elif existing != desired:
            save_existing(core_config, Path('core-config.toml'))
            core_config.parent.mkdir(parents=True, exist_ok=True)
            core_config.write_text('shell = '+json.dumps(desired)+'\n'+contents, encoding='utf-8')
            print('Shell recovery configured for the next core start. Running terminals were not restarted.')
    env = os.environ.copy(); env['HERDR_APP_HOME'] = str(app_home)
    for mod in manifest['mods']:
        subprocess.run([str(app),'check',str(app_home/'mods'/mod)],env=env,check=True)
    if not args.skip_activate:
        result = subprocess.run([str(app),'do','layout.switch',json.dumps({'name':layout_name})],env=env)
        if result.returncode:
            print('Import finished. Reopen Herdr and choose '+layout_name+' in Settings > Look.')
    print('Installed '+layout_name+' custom layout:',app_home)
    print('Backups of replaced files:',backup)
    return 0


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-home')
    parser.add_argument('--runtime-dir')
    parser.add_argument('--skip-activate',action='store_true')
    parser.add_argument('--enable-session-recovery',action='store_true')
    try: sys.exit(install(parser.parse_args()))
    except Exception as error:
        print('Import failed:',error,file=sys.stderr)
        sys.exit(1)
