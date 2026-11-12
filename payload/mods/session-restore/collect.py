"""Read-only WSL process/session inventory. No chat content is returned or saved."""
import concurrent.futures
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import subprocess
import sys

UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")


def safe_options(argv):
    """Keep launch settings, never a positional prompt or a previous image."""
    switches = {"--yolo", "--full-auto", "--no-alt-screen", "--no-daemon", "--search",
                "--dangerously-bypass-approvals-and-sandbox"}
    pairs = {"-m", "--model", "-p", "--profile", "-s", "--sandbox", "-a",
             "--ask-for-approval", "-c", "--config", "--enable", "--disable"}
    result = []
    i = 1
    while i < len(argv):
        value = argv[i]
        if value in switches:
            result.append(value)
        elif value in pairs and i + 1 < len(argv):
            result.extend(argv[i:i + 2])
            i += 1
        elif any(value.startswith(key + "=") for key in pairs):
            result.append(value)
        elif value in {"-C", "--cd", "-i", "--image"}:
            i += 1
        elif value in {"resume", "fork"}:
            break
        elif not value.startswith("-"):
            break
        i += 1
    return result


def processes():
    result = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            argv = [s.decode() for s in (path / "cmdline").read_bytes().split(b"\0") if s]
            if not argv or Path(argv[0]).name != "codex":
                continue
            if any(s in argv[1:3] for s in ("app-server", "exec", "review", "exec-server")):
                continue
            if not os.readlink(path / "fd/0").startswith("/dev/pts/"):
                continue
            env = dict(s.split("=", 1) for s in (path / "environ").read_bytes().decode().split("\0") if "=" in s)
            stat = (path / "stat").read_text().rsplit(")", 1)[1].split()
            result.append({"pid": int(path.name), "start": stat[19], "argv": argv,
                           "cwd": os.readlink(path / "cwd"), "env": env,
                           "user": pwd.getpwuid(path.stat().st_uid).pw_name})
        except (OSError, UnicodeError, ValueError):
            continue
    return result


def windows_ancestors(proc):
    # Selecting this WSL interop instance makes the Windows child a descendant
    # of the *same pane's* wsl.exe. No folder/title guessing is used for pane IDs.
    script = r"""$all=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId);
$current=$PID;$ids=@();for($i=0;$i -lt 14;$i++){
$row=$all | Where-Object ProcessId -eq $current | Select-Object -First 1;
if(-not $row){break};$ids += [int]$row.ProcessId;$current=$row.ParentProcessId};
ConvertTo-Json -Compress -InputObject @($ids)"""
    r = subprocess.run(["/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
                        "-NoProfile", "-NonInteractive", "-Command", script],
                       env=proc["env"], capture_output=True, text=True, timeout=18)
    return json.loads(r.stdout) if r.returncode == 0 else []


def clean_title(value):
    return re.sub(r"^[^\w]+", "", value, flags=re.UNICODE).rsplit(" | ", 1)[0].strip()


def strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "text" and isinstance(item, str):
                yield item
            elif isinstance(item, (list, dict)):
                yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def disambiguate(home, candidates, screen):
    """Require a unique 48-character transcript match; never choose 'latest'."""
    screen = re.sub(r"\s+", "", re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", screen))
    if len(screen) < 48:
        return None
    matches = []
    try:
        db = sqlite3.connect(f"file:{home}/thread_history_1.sqlite?mode=ro", uri=True, timeout=2)
        for row in candidates:
            found = False
            for (item,) in db.execute("select item_json from thread_items where thread_id=? "
                                     "and item_type in ('userMessage','agentMessage') "
                                     "order by rollout_ordinal desc limit 50", (row["id"],)):
                for text in strings(json.loads(item)):
                    text = re.sub(r"\s+", "", text)
                    if any(text[i:i + 48] in screen for i in range(0, max(0, len(text) - 47), 12)):
                        found = True
                        break
                if found:
                    break
            if found:
                matches.append(row)
        db.close()
    except (sqlite3.Error, ValueError):
        return None
    return matches[0] if len(matches) == 1 else None


def resolve(proc, terminal):
    home = proc["env"].get("CODEX_HOME", str(Path.home() / ".codex"))
    try:
        db = sqlite3.connect(f"file:{home}/state_5.sqlite?mode=ro", uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute("select id,title,name,cwd from threads where archived=0 and source in ('cli','vscode')")]
        db.close()
    except sqlite3.Error:
        return None, "Codex session database unavailable"
    explicit = next((a for a in proc["argv"][1:] if UUID.fullmatch(a)), None)
    title = clean_title(terminal.get("title", ""))
    screen = terminal.get("screen_text", "")
    status = re.search(r"\bSession:\s*([0-9a-f-]{36})", screen)
    if status:
        row = next((r for r in rows if r['id'] == status[1] and r['cwd'] == proc['cwd']
                    and (not title or title in (r['title'], r['name'], Path(proc['cwd']).name))), None)
        if row:
            return row['id'], 'status-session-id'
    candidates = [r for r in rows if r["cwd"] == proc["cwd"] and
                  (r["id"] == explicit if explicit else title and title in (r["title"], r["name"]))]
    if len(candidates) == 1:
        return candidates[0]["id"], "explicit-id" if explicit else "unique-title-and-folder"
    if len(candidates) > 1:
        match = disambiguate(home, candidates, terminal.get("screen_text", ""))
        if match:
            return match["id"], "title-folder-and-transcript"
        return None, "ambiguous-session"
    if "Resume a previous session" in screen or "Resume a previous chat" in screen:
        return None, "resume-picker"
    match = disambiguate(home, [r for r in rows if r['cwd'] == proc['cwd']], screen)
    if match:
        return match['id'], 'folder-and-transcript'
    if (title == Path(proc['cwd']).name and 'OpenAI Codex' in screen
            and not re.search(r'^\s*›\s+(?!Ask Codex|$)\S', screen, re.M)
            and not re.search(r'^\s*•\s', screen, re.M)):
        return None, 'fresh-cli'
    return None, "unidentified-session"


def inventory(request):
    kernel_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    init_start = Path('/proc/1/stat').read_text().rsplit(')', 1)[1].split()[19]
    # WSL distributions can restart while a sibling keeps the shared kernel up.
    boot = kernel_boot + ':' + init_start
    roots = {int(t["pid"]): t for t in request.get("terminals", []) if t.get("pid")}
    cache = request.get("process_cache", {}) if request.get("boot_id") == boot else {}
    procs = processes()
    mapped = []
    def map_one(proc):
        key = f"{proc['pid']}:{proc['start']}"
        saved = cache.get(key)
        if saved and saved.get("root_pid") in roots:
            return proc, key, saved
        try:
            ancestors = windows_ancestors(proc)
        except (subprocess.SubprocessError, ValueError, OSError):
            ancestors = []
        root = next((pid for pid in ancestors if pid in roots), None)
        return proc, key, {"root_pid": root}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for proc, key, saved in pool.map(map_one, procs):
            if not saved["root_pid"]:
                continue
            cache[key] = saved
            terminal = roots[saved["root_pid"]]
            session, evidence = resolve(proc, terminal)
            home = proc["env"].get("CODEX_HOME", str(Path.home() / ".codex"))
            mapped.append({"terminal": terminal["address"], "root_pid": saved["root_pid"],
                           "linux_pid": proc["pid"], "linux_start": proc["start"],
                           "boot_id": boot, "distro": proc["env"].get("WSL_DISTRO_NAME", os.environ.get("WSL_DISTRO_NAME", "Ubuntu-24.04")),
                           "user": proc["user"], "cwd": proc["cwd"], "codex_home": home,
                           "path": proc['env'].get('PATH', ''),
                           "session_id": session, "evidence": evidence,
                           "codex": shutil.which(proc["argv"][0], path=proc["env"].get("PATH")) or proc["argv"][0],
                           "options": safe_options(proc["argv"]),
                           "title": terminal.get("title", "")})
    current = {f"{p['pid']}:{p['start']}" for p in procs}
    return {"boot_id": boot, "records": mapped,
            "process_cache": {k: v for k, v in cache.items() if k in current}}


if __name__ == "__main__":
    print(json.dumps(inventory(json.load(sys.stdin)), ensure_ascii=False))
