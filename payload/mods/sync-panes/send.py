#!/usr/bin/env python3
# Types input into terminals the way a person at each would: attached to it
# (hc connect, framed mode, terminal.attach), writing the bytes their keys
# send. Unlike `hc keys`, this never waits for a person to stop typing, and
# unlike a paste it needs no clipboard or focus.
#
# argv[1]: a file (deleted once read) holding
#   {"terminals": ["t7", ...], "input": [{"text": "ls |"}, {"key": "enter", "mods": 0}, ...]}
# mods: 1 shift, 2 alt, 4 ctrl. Prints {"t7": null | "why it failed", ...}.
#
# Keys are encoded for each terminal's keyboard modes, read from the first
# paint the core sends a new viewer and followed in its live output: like
# Ghostty (which `hc keys` uses) for legacy, application cursor keys and
# kitty flags 1, 2 and 4. Anything else (other kitty flags, modifyOtherKeys
# with a modifier, modes it lost track of) goes through `hc keys` for that
# key, which may wait for the quiet the core keeps after typing.
#
# The attach asks for size 0x0, which the core never applies, so the
# terminal keeps the size Herdr gave it.
import json, os, re, struct, subprocess, sys, threading, time

HC = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "herdr-core", "hc.exe") if os.name == "nt" else "hc"

DATA, CREDIT, CLOSE = 0, 1, 2
GAP = 0.03      # between keys, as hc keys does: a lone Esc and what follows stay apart
DEADLINE = 25   # seconds; the mod's exec gives up at 30
CSI = "\x1b["
ARROWS = {"up": "A", "down": "B", "right": "C", "left": "D", "home": "H", "end": "F", "f1": "P", "f2": "Q", "f4": "S"}
TILDE = {"insert": 2, "delete": 3, "pageup": 5, "pagedown": 6, "f5": 15, "f6": 17, "f7": 18,
         "f8": 19, "f9": 20, "f10": 21, "f11": 23, "f12": 24}
CODES = {"enter": 13, "tab": 9, "backspace": 127, "esc": 27, "space": 32}
PLAIN = {"enter": "\r", "tab": "\t", "backspace": "\x7f", "esc": "\x1b", "space": " "}
CTRL = {"2": "\x00", "3": "\x1b", "4": "\x1c", "5": "\x1d", "6": "\x1e", "7": "\x1f", "8": "\x7f",
        "[": "\x1b", "\\": "\x1c", "]": "\x1d", "/": "\x1f", "1": "1", "9": "9", "0": "0"}


class Modes:
    def __init__(self):
        self.cursor = False   # DECCKM: application cursor keys
        self.kitty = 0        # kitty keyboard flags; None: lost track
        self.other = 0        # xterm modifyOtherKeys
        self.painted = False  # the first paint (it ends with ?9001) is in

    def feed(self, s):
        for m in re.finditer(r"\x1bc|\x1b\[([?=<>]?)([0-9;:]*)([a-zA-Z~])", s):
            if m.group(0) == "\x1bc":
                self.cursor, self.kitty, self.other = False, 0, 0
                continue
            lead, params, final = m.groups()
            nums = [int(p) if p.isdigit() else 0 for p in params.split(";")] if params else []
            if lead == "?" and final in "hl":
                for n in nums:
                    if n == 1:
                        self.cursor = final == "h"
                    elif n in (47, 1047, 1049) and self.painted:
                        self.kitty = None  # each screen has its own kitty flags
                    elif n == 9001:
                        self.painted = True
            elif lead == "=" and final == "u" and nums and self.kitty is not None:
                how = nums[1] if len(nums) > 1 else 1
                self.kitty = {1: nums[0], 2: self.kitty | nums[0], 3: self.kitty & ~nums[0]}.get(how, None)
            elif lead == ">" and final == "u":
                self.kitty = nums[0] if nums else 0
            elif lead == "<" and final == "u":
                self.kitty = None  # a pop: what's under it isn't known here
            elif lead == ">" and final == "m" and nums and nums[0] == 4:
                self.other = nums[1] if len(nums) > 1 else 0


def encode(key, mods, modes):
    """The bytes this key sends, "" for none, None when only hc keys knows."""
    flags = modes.kitty
    if flags is None or flags & ~7:
        return None
    m = mods + 1
    if flags:
        event = ":1" if flags & 2 else ""
        if key == "f3":
            return CSI + "13" + (f";{m}" if mods else "") + "~"
        if key in ARROWS:
            return f"{CSI}1;{m}{event}{ARROWS[key]}" if mods or event else CSI + ARROWS[key]
        if key in TILDE:
            return CSI + str(TILDE[key]) + (f";{m}" if mods else "") + "~"
        code = CODES.get(key, ord(key) if len(key) == 1 else None)
        if code is None:
            return None
        if not mods:
            return CSI + "27u" if key == "esc" else PLAIN.get(key, key)
        return f"{CSI}{code};{m}u"
    if key in ARROWS:
        if mods:
            return f"{CSI}1;{m}{ARROWS[key]}"
        return ("\x1bO" if modes.cursor or key.startswith("f") else CSI) + ARROWS[key]
    if key == "f3":
        return f"{CSI}1;{m}R" if mods else "\x1bOR"
    if key in TILDE:
        return CSI + str(TILDE[key]) + (f";{m}" if mods else "") + "~"
    if modes.other and mods:
        return None
    shift, alt, ctrl = mods & 1, mods & 2, mods & 4
    esc = "\x1b" if alt else ""
    if key in ("enter", "tab", "esc"):
        if key == "tab" and mods == 1:
            return CSI + "Z"
        if shift or ctrl:
            return f"{CSI}27;{m};{CODES[key]}~"
        return esc + PLAIN[key]
    if key == "backspace":
        return esc + ("\x08" if ctrl else "\x7f")
    if key == "space":
        return esc + ("\x00" if ctrl else " ")
    if len(key) != 1:
        return None
    if ctrl:
        if "a" <= key <= "z":
            return esc + chr(ord(key) & 0x1F)
        return esc + CTRL[key] if key in CTRL else ""
    return esc + (key.upper() if shift else key)


def hc_name(key, mods):
    names = [n for bit, n in ((4, "ctrl"), (2, "alt"), (1, "shift")) if mods & bit]
    return "+".join(names + [{"\\": "backslash"}.get(key, key)])


class Conn:
    def __init__(self):
        self.p = subprocess.Popen([HC, "connect"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        self.lock = threading.Lock()
        self.ids = 1
        self.replies = {}
        self.streams = {}
        self.cond = threading.Condition()
        hello = {"jsonrpc": "2.0", "id": 0, "method": "hello", "params": {"framed": True, "generation": 1}}
        self.p.stdin.write((json.dumps(hello) + "\n").encode())
        reply = json.loads(self.p.stdout.readline() or "{}")
        if "result" not in reply:
            raise RuntimeError(reply.get("error", {}).get("message", "hc connect failed"))
        threading.Thread(target=self.read, daemon=True).start()

    def frame(self, channel, kind, payload=b""):
        with self.lock:
            self.p.stdin.write(struct.pack("<IBI", channel, kind, len(payload)) + payload)

    def exact(self, n):
        b = b""
        while len(b) < n:
            c = self.p.stdout.read(n - len(b))
            if not c:
                raise EOFError
            b += c
        return b

    def read(self):
        try:
            while True:
                channel, kind, n = struct.unpack("<IBI", self.exact(9))
                payload = self.exact(n)
                with self.cond:
                    if channel == 0:
                        msg = json.loads(payload)
                        self.replies[msg.get("id")] = msg
                    else:
                        # The first paint can come before type_into has the channel.
                        self.streams.setdefault(channel, Stream()).take(kind, payload)
                        if kind == DATA:
                            self.frame(channel, CREDIT, struct.pack("<I", n))
                    self.cond.notify_all()
        except (EOFError, OSError, ValueError):
            with self.cond:
                self.replies["closed"] = True
                self.cond.notify_all()

    def wait(self, test, until):
        with self.cond:
            while not test():
                if "closed" in self.replies:
                    raise RuntimeError("hc closed the connection")
                left = until - time.time()
                if left <= 0:
                    raise TimeoutError("timed out")
                self.cond.wait(left)

    def call(self, method, params, until):
        with self.lock:
            self.ids += 1
            i = self.ids
        msg = {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
        self.frame(0, DATA, json.dumps(msg).encode())
        self.wait(lambda: i in self.replies, until)
        reply = self.replies.pop(i)
        if "error" in reply:
            err = reply["error"]
            raise RuntimeError((err.get("data") or {}).get("message") or err.get("message") or "failed")
        return reply["result"]


class Stream:
    def __init__(self):
        self.modes = Modes()
        self.carry = ""
        self.closed = False

    def take(self, kind, payload):
        if kind == CLOSE:
            self.closed = True
            return
        if kind != DATA:
            return
        s = self.carry + payload.decode("latin-1")
        # Keep an escape sequence cut by the frame's end for the next one.
        cut = s.rfind("\x1b")
        if cut >= 0 and not re.match(r"\x1bc|\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]", s[cut:]) and len(s) - cut < 64:
            s, self.carry = s[:cut], s[cut:]
        else:
            self.carry = ""
        self.modes.feed(s)


def type_into(conn, terminal, items, until):
    reply = conn.call("terminal.attach", {"terminal": terminal, "cols": 0, "rows": 0, "history": 0}, until)
    channel = reply["channel"]
    with conn.cond:
        stream = conn.streams.setdefault(channel, Stream())
    try:
        conn.wait(lambda: stream.modes.painted or stream.closed, min(until, time.time() + 5))
        last = None
        for item in items:
            if stream.closed:
                raise RuntimeError("the terminal went away")
            kind = "text" if "text" in item else "key"
            if last == "key" or (last and kind == "key"):
                time.sleep(GAP)
            last = kind
            if kind == "text":
                conn.frame(channel, DATA, item["text"].encode())
                continue
            with conn.cond:
                data = encode(item["key"], item.get("mods", 0), stream.modes)
            if data is None:
                conn.call("terminal.keys", {"terminal": terminal, "keys": [hc_name(item["key"], item.get("mods", 0))]}, until)
            elif data:
                conn.frame(channel, DATA, data.encode())
    finally:
        # The core reads frames in order: its CLOSE means our input has
        # gone to the program's terminal.
        if not stream.closed:
            conn.frame(channel, CLOSE)
            conn.wait(lambda: stream.closed, min(until, time.time() + 2))


def main():
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            req = json.load(f)
    finally:
        os.unlink(sys.argv[1])
    until = time.time() + DEADLINE
    out = {t: "not sent" for t in req["terminals"]}
    try:
        conn = Conn()
    except Exception as e:
        print(json.dumps({t: str(e) or "hc connect failed" for t in req["terminals"]}))
        return

    def one(t):
        try:
            type_into(conn, t, req["input"], until)
            out[t] = None
        except Exception as e:
            out[t] = str(e) or type(e).__name__

    threads = [threading.Thread(target=one, args=(t,), daemon=True) for t in req["terminals"]]
    for th in threads:
        th.start()
    for th in threads:
        th.join(max(0, until - time.time()) + 1)
    print(json.dumps(out))
    sys.stdout.flush()
    conn.p.stdin.close()


if __name__ == "__main__":
    main()
