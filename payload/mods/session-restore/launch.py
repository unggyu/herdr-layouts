"""Run one saved Codex conversation, without replaying a task or prompt."""
import fcntl
import json
import os
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from options import build_argv

def main():
    state_path, terminal = sys.argv[1:3]
    entry = sys.argv[3] if len(sys.argv)>3 else None
    record = json.loads(Path(state_path).read_text())["records"][terminal]
    if entry:
        import sqlite3
        with sqlite3.connect(str(Path(state_path).parent/'history.sqlite')) as db:
            row=db.execute('SELECT terminal,record FROM entries WHERE id=?',(entry,)).fetchone()
        if not row or row[0]!=terminal: raise ValueError('Pane mismatch')
        record=json.loads(row[1])
    if not entry and not record.get("armed"):
        raise ValueError("This terminal was intentionally left or closed")
    if not Path(record["cwd"]).is_dir():
        raise ValueError("The saved working directory no longer exists")
    lock_dir = Path.home() / ".local/state/herdr-session-restore/locks"
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = open(lock_dir / (record.get("session_id") or terminal), "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError("This conversation already has a recovery process")
    os.set_inheritable(lock.fileno(), True)
    os.chdir(record["cwd"])
    env = os.environ.copy()
    env["CODEX_HOME"] = record["codex_home"]
    if record.get('path'):
        env['PATH'] = record['path']
    env["HC_TERMINAL_ID"] = terminal
    argv = build_argv(record)
    os.execvpe(argv[0], argv, env)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[Herdr recovery] {error}", file=sys.stderr)
        sys.exit(1)
