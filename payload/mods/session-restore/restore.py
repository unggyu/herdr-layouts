"""Configured Windows shell: reopen a saved chat, otherwise use PowerShell."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from service import DATA, ROOT, STATE, WSL, read_state, win_to_wsl


def wsl_command(record, terminal):
    return [str(WSL), "-d", record["distro"], "-u", record["user"], "--cd", record["cwd"],
            "--exec", "/usr/bin/python3", win_to_wsl(ROOT / "launch.py"), win_to_wsl(STATE), terminal]


def restore(terminal):
    record = read_state()["records"].get(terminal)
    if not record or not record.get("armed"):
        return False
    import msvcrt
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / ("pane-" + terminal + ".lock")).open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        print("[Herdr] Restoring saved Codex conversation...", flush=True)
        subprocess.call(wsl_command(record, terminal))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal", default=os.environ.get("HC_TERMINAL_ID"))
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args()
    if args.shell and os.environ.get('HC_SESSION', 'default') == 'default' and not os.environ.get('HERDR_RECOVERY_DATA'):
        # Also start tracking when a built-in layout, rather than our personal
        # layout, creates the first terminal. The service lock deduplicates it.
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        subprocess.Popen([str(pythonw), '-I', str(ROOT / 'service.py'), '--watch'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    if args.terminal and (os.environ.get("HC_SESSION", "default") == "default" or os.environ.get("HERDR_RECOVERY_DATA")):
        restore(args.terminal)
    if args.shell:
        original = json.loads((ROOT / "original-shell.json").read_text(encoding="utf-8"))
        # Inherit this terminal's cwd and refreshed environment as Herdr does.
        subprocess.call(original)


if __name__ == "__main__":
    main()
