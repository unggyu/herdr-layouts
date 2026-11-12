"""Windows-side snapshot/recovery service for existing Herdr panes."""
import argparse
import concurrent.futures
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("HERDR_RECOVERY_DATA", ROOT / "data"))
STATE = DATA / "sessions.json"
HC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/herdr-core/hc.exe"
APP = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/herdr-app/herdr-app.exe"
WSL = Path(os.environ.get("SystemRoot", "__WINDOWS_ROOT__")) / "System32/wsl.exe"
FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def execute(argv, timeout=20, **kwargs):
    result = subprocess.run([str(a) for a in argv], capture_output=True, encoding="utf-8",
                            errors="replace", timeout=timeout, **FLAGS, **kwargs)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-500:])
    return result.stdout


def hc(*args):
    return execute([HC, *args])


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def read_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "records": {}, "distros": {}}


def log(message):
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "recovery.log"
    if path.exists() and path.stat().st_size > 200_000:
        path.replace(DATA / "recovery.previous.log")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")


def win_to_wsl(path):
    value = str(path).replace("\\", "/")
    if not re.match(r"^[A-Za-z]:/", value):
        raise ValueError("Recovery files must be on a Windows drive")
    return "/mnt/" + value[0].lower() + "/" + value[3:]


def running_distros():
    r = subprocess.run([str(WSL), "--list", "--running", "--quiet"], capture_output=True,
                       timeout=10, **FLAGS)
    raw = r.stdout
    text = raw.decode("utf-16-le", errors="replace") if b"\0" in raw else raw.decode("utf-8", errors="replace")
    return [s.strip().lstrip("\ufeff") for s in text.splitlines() if s.strip()]


def terminal_info():
    listed = json.loads(hc("ls", "--json"))["terminals"]
    def one(item):
        detail = json.loads(hc("get", item["address"], "--json"))
        if not detail.get("keep") or not detail.get("labels", {}).get("herdr.tab"):
            return None
        detail["screen_text"] = hc("read", item["address"], "--lines", "0")
        return detail
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        return [t for t in pool.map(one, listed) if t]


def inventory(distro, terminals, prior):
    request = {"terminals": [{"address": t["address"], "pid": t.get("pid"),
                               "title": t.get("title", ""), "screen_text": t.get("screen_text", "")}
                              for t in terminals],
               "boot_id": prior.get("boot_id"), "process_cache": prior.get("process_cache", {})}
    output = execute([WSL, "-d", distro, "--exec", "/usr/bin/python3", win_to_wsl(ROOT / "collect.py")],
                     input=json.dumps(request, ensure_ascii=False), timeout=90)
    return json.loads(output)


def should_restore(record, boot, terminal, current_panes):
    if not record.get("armed") or record["terminal"] in current_panes:
        return False
    if not terminal or terminal.get("state") != "live" or not terminal.get("keep"):
        return False
    if not (record["boot_id"] != boot or record.get("root_pid") != terminal.get("pid")):
        return False
    if record.get("pending_until", 0) > time.time():
        return False
    # Never erase a draft or type into a program. An unchanged idle PowerShell
    # prompt is mandatory, and recovery is only eligible after a boot/root change.
    screen = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", terminal.get("screen_text", "")).rstrip()
    return bool(re.search(r"(?:^|\n)PS [^\r\n>]+>\s*$", screen))


def send_restore(terminal):
    """A verified empty shell prompt only; never send a Codex task or message."""
    spec = importlib.util.spec_from_file_location("recovery_input", ROOT / "terminal_input.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command = "& '" + str(Path(sys.executable)).replace("'", "''") + "' -I '" + str(ROOT / "restore.py").replace("'", "''") + "' --terminal " + terminal
    connection = module.Conn()
    try:
        module.type_into(connection, terminal, [{"text": command}, {"key": "enter", "mods": 0}], time.time() + 25)
    finally:
        connection.p.stdin.close()


def tick(recover=True):
    state = read_state()
    terminals = terminal_info()
    by_id = {t["address"]: t for t in terminals}
    restored, unresolved = [], []
    for distro in running_distros():
        if distro.startswith("docker-"):
            continue
        prior = state["distros"].get(distro, {})
        observed = inventory(distro, terminals, prior)
        current_panes = {r["terminal"] for r in observed["records"]}
        for record in observed["records"]:
            terminal = by_id[record["terminal"]]
            if record["session_id"] or record["evidence"] in ("resume-picker", "fresh-cli"):
                record.update(armed=True, saved_at=time.time(), labels=terminal.get("labels", {}))
                state["records"][record["terminal"]] = record
                # Core metadata, not keystrokes: expose the verified identity on
                # its actual pane and persist it with Herdr's own terminal state.
                labels = {'recovery.codex-session': record['session_id'] or '',
                          'recovery.wsl-distro': record['distro'],
                          'recovery.linux-cwd': record['cwd']}
                changes = [f'{key}={value}' for key, value in labels.items()
                           if terminal.get('labels', {}).get(key) != value]
                if changes:
                    hc('label', record['terminal'], *changes)
            else:
                unresolved.append({"terminal": record["terminal"], "reason": record["evidence"]})
                # Never retain an old ID when the user switched to an unknown chat.
                if record["terminal"] in state["records"]:
                    state["records"][record["terminal"]]["armed"] = False
        for address, record in state["records"].items():
            if record["distro"] != distro or address in current_panes:
                continue
            terminal = by_id.get(address)
            if terminal is None:
                record["armed"] = False
            elif record["boot_id"] == observed["boot_id"] and record.get("root_pid") == terminal.get("pid"):
                # A normal exit isn't a restart. Do not resurrect it later.
                record["armed"] = False
            elif recover and should_restore(record, observed["boot_id"], terminal, current_panes):
                # Mark before dispatch so a crash cannot enqueue the command twice.
                record["pending_until"] = time.time() + 180
                atomic_json(STATE, state)
                fresh = json.loads(hc("get", address, "--json"))
                fresh["screen_text"] = hc("read", address, "--lines", "0")
                if should_restore({**record, "pending_until": 0}, observed["boot_id"], fresh, current_panes):
                    send_restore(address)
                    restored.append(address)
                    log(f"Resumed saved conversation in {address}")
        state["distros"][distro] = {"boot_id": observed["boot_id"], "process_cache": observed["process_cache"]}
    for address, record in state["records"].items():
        if address not in by_id:
            record["armed"] = False
    state["unresolved"] = unresolved
    state["updated_at"] = time.time()
    state['identity_mode'] = 'passive-no-terminal-input'
    atomic_json(STATE, state)
    return {"saved": sum(r.get("armed", False) for r in state["records"].values()),
            "unresolved": unresolved, "restored": restored}


def watch():
    if (DATA / "PAUSED").exists():
        return
    # One service across layout reloads/windows, without a shell or extra console.
    import msvcrt
    DATA.mkdir(parents=True, exist_ok=True)
    lock = (DATA / "service.lock").open("a+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    atomic_json(DATA / "service.json", {"pid": os.getpid(), "started_at": time.time()})
    log("Passive snapshot/recovery service started; identity lookup never types into terminals")
    dirty = threading.Event()
    stopped = threading.Event()
    event_process = [None]
    def changes():
        titles = {}
        while not stopped.is_set():
            try:
                process = subprocess.Popen([str(HC), 'events', '--json'], stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                           errors='replace', **FLAGS)
                event_process[0] = process
                for line in process.stdout:
                    event = json.loads(line)
                    params = event.get('params', event)
                    kind = params.get('type')
                    if kind == 'title':
                        title = re.sub(r'^[^\w]+', '', params.get('data', {}).get('title', ''))
                        address = params.get('terminal')
                        if titles.get(address) == title:
                            continue  # spinner frames aren't session changes
                        titles[address] = title
                    if kind in ('title', 'turn', 'created', 'restarted', 'lost', 'finished', 'removed'):
                        dirty.set()
                    if stopped.is_set():
                        break
            except Exception:
                pass
            if not stopped.is_set():
                stopped.wait(5)
    threading.Thread(target=changes, daemon=True).start()
    # Opening Herdr is the user's signal to wake previously saved distributions.
    for distro in {r["distro"] for r in read_state()["records"].values() if r.get("armed")}:
        try:
            execute([WSL, "-d", distro, "--exec", "/bin/true"], timeout=30)
        except Exception as error:
            log(f"WSL startup failed: {type(error).__name__}")
    while True:
        try:
            execute([APP, "status"], timeout=10)
        except Exception:
            log("Herdr window closed; service stopped")
            stopped.set()
            if event_process[0] is not None:
                event_process[0].terminate()
            return
        try:
            result = tick()
            if result["unresolved"]:
                log("Unresolved panes: " + ",".join(r["terminal"] for r in result["unresolved"]))
        except Exception as error:
            log(f"Snapshot failed: {type(error).__name__}: {error}")
        if dirty.wait(30):
            dirty.clear()
            stopped.wait(2)  # coalesce a title/turn burst and let Codex persist its ID


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    args = parser.parse_args()
    if args.watch:
        watch()
    else:
        print(json.dumps(tick(recover=not args.scan_only), ensure_ascii=False))
