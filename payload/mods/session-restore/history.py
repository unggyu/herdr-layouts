"""Durable Windows-side pane history and explicit recovery API."""
import argparse, json, re, sqlite3, time, uuid, subprocess
from pathlib import Path
import sys, shlex
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import service as s
from options import build_argv

def clean(title):
    return re.sub(r"^[^\w]+", "", title or "").strip()

def connect():
    s.DATA.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(s.DATA / 'history.sqlite', timeout=15)
    db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, terminal TEXT, title TEXT, stamp REAL, record TEXT)')
    return db

def save(terminal, title, record=None):
    title=clean(title)
    if not title: return
    with connect() as db:
        previous=db.execute('SELECT id,title,record FROM entries WHERE terminal=? ORDER BY stamp DESC LIMIT 1',(terminal,)).fetchone()
        payload=json.dumps(record,ensure_ascii=False) if record else None
        if previous and previous[1]==title:
            old=json.loads(previous[2]) if previous[2] else None
            if not record or old and old.get('session_id')==record.get('session_id'):
                return
            if not old:
                db.execute('UPDATE entries SET record=? WHERE id=?',(payload,previous[0]));return
        db.execute('INSERT INTO entries VALUES (?,?,?,?,?)',(str(uuid.uuid4()),terminal,title,time.time(),payload))
        db.execute('DELETE FROM entries WHERE terminal=? AND id NOT IN (SELECT id FROM entries WHERE terminal=? ORDER BY stamp DESC LIMIT 100)',(terminal,terminal))

def seed():
    for terminal,record in s.read_state().get('records',{}).items():
        with connect() as db:
            exists=db.execute('SELECT 1 FROM entries WHERE terminal=? LIMIT 1',(terminal,)).fetchone()
        if not exists: save(terminal,record.get('title'),record)

def entries():
    seed()
    with connect() as db:
        rows=db.execute('SELECT id,terminal,title,stamp,record FROM entries ORDER BY stamp DESC').fetchall()
    return [dict(id=i,terminal=t,title=n,stamp=d,record=json.loads(v) if v else None) for i,t,n,d,v in rows]

def lookup(entry):
    with connect() as db:
        row=db.execute('SELECT terminal,record FROM entries WHERE id=?',(entry,)).fetchone()
    if not row or not row[1]: raise ValueError('대화 ID가 없습니다. 이전 기록을 선택하세요.')
    return row[0],json.loads(row[1])

def eligible(info,screen):
    foreground=info.get('foreground') or {}
    name=(foreground.get('name') or '').lower()
    return (info.get('state')=='live' and info.get('keep') and name in ('','powershell.exe','pwsh.exe')
            and bool(re.search(r'(?:^|\n)PS [^\r\n>]+>\s*$',screen.rstrip())))

def dispatch(entry):
    terminal,record=lookup(entry)
    if not record.get('session_id'): raise ValueError('저장된 대화 ID가 없습니다.')
    info=json.loads(s.hc('get',terminal,'--json'))
    if not eligible(info,s.hc('read',terminal,'--lines','0')):
        raise ValueError('실행 중인 프로그램 또는 입력이 있습니다. 빈 PowerShell 프롬프트에서 복구하세요.')
    if not re.fullmatch(r't[0-9a-z]+',terminal): raise ValueError('지원하지 않는 터미널입니다.')
    for distro in s.running_distros():
        if distro.startswith('docker-'): continue
        observed=s.inventory(distro,s.terminal_info(),s.read_state().get('distros',{}).get(distro,{}))
        if any(v.get('session_id')==record['session_id'] for v in observed['records']):
            raise ValueError('이 대화가 이미 다른 pane에서 실행 중입니다.')
    s.send_restore(terminal,entry)
    deadline=time.time()+60
    while time.time()<deadline:
        info=json.loads(s.hc('get',terminal,'--json'))
        if (info.get('foreground') or {}).get('name','').lower()=='wsl.exe':
            observed=s.inventory(record['distro'],[info],{})
            if any(v.get('session_id')==record['session_id'] for v in observed['records']):
                return {'status':'restored','terminal':terminal}
        time.sleep(2)
    return {'status':'failed','terminal':terminal,'error':'대화 재개를 확인하지 못했습니다. pane 화면을 확인하세요.'}

def candidates(entry, chosen_id=None):
    with connect() as db:
        row=db.execute('SELECT terminal FROM entries WHERE id=?',(entry,)).fetchone()
        prior=db.execute('SELECT record FROM entries WHERE terminal=? AND record IS NOT NULL ORDER BY stamp DESC LIMIT 1',(row[0],)).fetchone() if row else None
    if not prior: raise ValueError('배포판과 폴더 기록이 없습니다. 이전 기록을 선택하세요.')
    record=json.loads(prior[0])
    script="import sqlite3,json,sys; d=sqlite3.connect('file:'+sys.argv[1]+'/state_5.sqlite?mode=ro',uri=True); print(json.dumps([dict(id=r[0],title=r[1],cwd=r[2]) for r in d.execute('select id,coalesce(name,title),cwd from threads where cwd=? and archived=0 order by updated_at desc limit 100',(sys.argv[2],))]))"
    result=s.execute([s.WSL,'-d',record['distro'],'-u',record['user'],'--exec','/usr/bin/python3','-c',script,record['codex_home'],record['cwd']],timeout=60)
    out=json.loads(result)
    if chosen_id:
        candidate=next((c for c in out if c['id']==chosen_id),None)
        if not candidate: raise ValueError('대화를 찾지 못했습니다.')
        chosen={**record,'session_id':candidate['id'],'title':candidate['title'],'evidence':'user-selected'}
        save(row[0],chosen['title'],chosen)
        return {'status':'selected'}
    return {'status':'candidates','candidates':out}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['list','restore','command','candidates']);parser.add_argument('--entry');parser.add_argument('--candidate')
    args=parser.parse_args()
    if args.action=='list': print(json.dumps(entries(),ensure_ascii=False))
    elif args.action=='candidates': print(json.dumps(candidates(args.entry,args.candidate),ensure_ascii=False))
    elif args.action=='command':
        terminal,record=lookup(args.entry)
        if not record.get('session_id'): raise ValueError('대화 ID를 먼저 선택하세요.')
        print(json.dumps({'command':'cd -- '+shlex.quote(record['cwd'])+' && '+shlex.join(build_argv(record))},ensure_ascii=False))
    else:
        import msvcrt
        with (s.DATA/'manual.lock').open('a+b') as lock:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            print(json.dumps(dispatch(args.entry),ensure_ascii=False))
if __name__=='__main__':
    try: main()
    except Exception as e: print(json.dumps({'error':str(e)},ensure_ascii=False));raise SystemExit(1)
