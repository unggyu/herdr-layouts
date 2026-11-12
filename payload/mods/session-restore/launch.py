"""Run one saved Codex conversation, without replaying a task or prompt."""
import fcntl
import json
import os
from pathlib import Path
import sys


def build_argv(record):
    result = [record["codex"], *record.get("options", [])]
    if record.get("session_id"):
        result.extend(["resume", record["session_id"]])
    elif record.get("evidence") == "resume-picker":
        result.append("resume")
    elif record.get("evidence") == "fresh-cli":
        pass
    else:
        raise ValueError("No verified Codex conversation is saved")
    return result


def main():
    state_path, terminal = sys.argv[1:3]
    record = json.loads(Path(state_path).read_text())["records"][terminal]
    if not record.get("armed"):
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
