"""Resolve a selected WSL/Windows path and reveal it in Windows Explorer."""
import argparse
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def selected_path(text):
    value = text.strip()
    pairs = {'(':')','[':']','<':'>','"':'"',"'":"'",'`':'`'}
    while len(value) >= 2 and pairs.get(value[0]) == value[-1]:
        value = value[1:-1].strip()
    match = re.search(r'file://|/home/|/mnt/|~/|[A-Za-z]:[\\/]|\\\\', value)
    if match and match.start():
        prefix = value[:match.start()]
        value = value[match.start():]
        if prefix.rstrip().endswith('('):
            depth = 1
            for index, char in enumerate(value):
                if char == '(': depth += 1
                elif char == ')': depth -= 1
                if depth == 0:
                    value = value[:index]
                    break
    return value


def windows_path(value, distro, cwd=''):
    if '\x00' in value or not value:
        raise ValueError('파일 경로를 선택한 뒤 다시 눌러주세요.')
    if value.startswith('file://'):
        parsed = urlparse(value)
        value = ('//' + parsed.netloc if parsed.netloc else '') + unquote(parsed.path)
        if re.match(r'^/[A-Za-z]:/',value):
            value=value[1:]
    if re.match(r'^[A-Za-z]:[\\/]',value) or value.startswith(('\\\\','//')):
        return ntpath.normpath(value)
    if value.startswith('~/'):
        # Herdr records the Linux cwd; resolve the current Linux user's home.
        match=re.match(r'^(/home/[^/]+)',cwd)
        if not match:
            raise ValueError('전체 /home/... 경로를 선택해주세요.')
        value=match[1]+'/'+value[2:]
    if not value.startswith('/'):
        if cwd.startswith('/'):
            value=cwd.rstrip('/')+'/'+value
        elif cwd:
            return ntpath.normpath(ntpath.join(cwd,value))
        else:
            raise ValueError('전체 파일 경로를 선택해주세요.')
    mounted=re.match(r'^/mnt/([a-zA-Z])(?:/(.*))?$',value)
    if mounted:
        return mounted[1].upper()+':\\'+(mounted[2] or '').replace('/','\\')
    if not distro:
        raise ValueError('이 pane의 WSL 배포판을 아직 확인하지 못했습니다.')
    return '\\\\wsl.localhost\\'+distro+value.replace('/','\\')



def path_candidates(text):
    """Prefer exact filenames; only then repair terminal wrapping/punctuation."""
    value = selected_path(text)
    variants = [value]
    if '\n' in value or '\r' in value:
        variants.append(''.join(line.strip() for line in value.splitlines()))
    seen = set()
    for variant in variants:
        current = variant
        while current and current not in seen:
            seen.add(current)
            yield current
            bare = re.sub(r':\d+(?::\d+)?$', '', current)
            if bare != current:
                current = bare
                continue
            tail = current[-1]
            opening = {')': '(', ']': '[', '}': '{', '>': '<'}.get(tail)
            if tail in '.,;' or (opening and current.count(tail) > current.count(opening)) or (tail in '\"\'`' and current.count(tail) % 2):
                current = current[:-1].rstrip()
                continue
            break


def resolve_existing_path(text, distro, cwd='', exists=None):
    exists = os.path.exists if exists is None else exists
    for candidate in path_candidates(text):
        target = windows_path(candidate, distro, cwd)
        if exists(target):
            return target
    raise ValueError('파일을 찾지 못했습니다. 경로 전체를 선택해주세요.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('terminal')
    parser.add_argument('--path')
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--action',choices=['reveal','open'],default='reveal')
    args=parser.parse_args()
    flags={'creationflags':subprocess.CREATE_NO_WINDOW}
    hc=Path(os.environ['LOCALAPPDATA'])/'Programs/herdr-core/hc.exe'
    r=subprocess.run([str(hc),'get',args.terminal,'--json'],capture_output=True,
                     encoding='utf-8',errors='replace',timeout=10,**flags)
    if r.returncode: raise ValueError(r.stderr or r.stdout)
    info=json.loads(r.stdout);labels=info.get('labels',{})
    if args.path is None:
        ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        script='[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); @{text=(Get-Clipboard -Raw)} | ConvertTo-Json -Compress'
        r=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-STA','-Command',script],
                         capture_output=True,encoding='utf-8',errors='replace',timeout=10,**flags)
        if r.returncode: raise ValueError(r.stderr)
        text=json.loads(r.stdout).get('text') or ''
    else:
        text=args.path
    distro=labels.get('recovery.wsl-distro')
    cwd=labels.get('recovery.linux-cwd') or info.get('cwd','')
    target=resolve_existing_path(text,distro,cwd)
    if not args.check_only:
        if args.action == 'open' or os.path.isdir(target):
            os.startfile(target, 'open')
        else:
            explorer=Path(os.environ['SystemRoot'])/'explorer.exe'
            subprocess.Popen([str(explorer),'/select,',target],**flags)
    print(json.dumps({'ok':True,'path':target,'directory':os.path.isdir(target),'action':args.action},ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False));sys.exit(1)
