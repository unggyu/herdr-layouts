import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).parent
hc=Path(os.environ['LOCALAPPDATA'])/'Programs/herdr-core/hc.exe'
flags={'creationflags':subprocess.CREATE_NO_WINDOW}
def capture(terminal):
    r=subprocess.run([str(hc),'get',terminal,'--json'],capture_output=True,encoding="utf-8",errors="replace",timeout=10,**flags)
    if r.returncode: raise RuntimeError(r.stderr or r.stdout)
    info=json.loads(r.stdout)
    pid=info.get('foreground',{}).get('pid') or info.get('pid') or 0
    ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    r=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-STA','-ExecutionPolicy','Bypass','-File',str(root/'capture.ps1'),'-TerminalProcessId',str(pid)],capture_output=True,encoding='utf-8',errors='replace',timeout=20,**flags)
    if r.returncode: raise RuntimeError(r.stderr or r.stdout)
    return json.loads(r.stdout.lstrip('\ufeff'))
def main():
    terminal=sys.argv[1]
    result=capture(terminal)
    if '--capture-only' in sys.argv or result['kind']!='image':
        print(json.dumps(result)); return
    spec=importlib.util.spec_from_file_location('terminal_input',root/'terminal_input.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    conn=module.Conn()
    try:
        module.type_into(conn,terminal,[{'text':'\x1b[200~'+result['path']+'\x1b[201~'}],time.time()+25)
    finally:
        conn.p.stdin.close()
    print(json.dumps({'kind':'image','wsl':result['wsl']}))
if __name__=='__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'error':str(e)}));sys.exit(1)
