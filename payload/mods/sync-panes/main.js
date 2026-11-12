// Types the same input into every terminal of one tab, like tmux's
// synchronize-panes. While this window has the keyboard, each key goes to
// all of them through send.py, which attaches to each terminal and types
// the bytes the key sends there (Python 3). It never touches the clipboard or
// focus, and doesn't wait for the quiet `hc keys` keeps after a person types.
// Cmd-V pastes the clipboard to all with `terminal.paste` on each pane.
//
// What it shows is what it sends: keys are only sent while the pill says
// Sync. Pausing (the keyboard went elsewhere), stopping, leaving the tab, a
// change in which panes are targeted and a failed send all drop what's
// still queued; a send already handed to send.py can't be called back. A failed
// send also holds input until the pill is clicked. The keys of a multi-key
// binding in keys.json ("ctrl-t n") run that binding instead of being typed.
// mod.open:sync-panes opens it and, again, closes it; so do sync-panes.stop
// (a key that only stops) and the ✕.

import { View, div } from "gpui-kit";
import { h_flex } from "gpui-base";
import * as fs from "fs/promises";
import { exec, appHome, writeTextFile, run, panes, focused, spaces, keys, commands, shared, theme, props, closeOverlay, notify, nextCommand, window } from "herdr";

const LABEL = {
  sync: (n, tab) => `Sync ${n} · ${tab}`,
  paused: "Paused",
  none: "No terminals",
  failed: (who) => `Failed ${who} · click to resume`,
  failedTitle: "Sync panes stopped sending",
  badSend: "This send: binding has characters that can't be typed; nothing was sent",
  noPython: "send.py needs Python 3, and none was found (python3, python, py -3)",
};

// GPUI key names -> send.py key names, where they differ.
const NAMED = {
  escape: "esc", enter: "enter", backspace: "backspace", tab: "tab", space: "space",
  up: "up", down: "down", left: "left", right: "right", home: "home", end: "end",
  pageup: "pageup", pagedown: "pagedown", delete: "delete", insert: "insert",
};
// send.py's modifier bits.
const SHIFT = 1, ALT = 2, CTRL = 4;
// The most input one send.py run carries.
const BATCH = 256;
// Herdr applies a pane focus after the mod's own focus call, so after
// moving focus (a paste, a pane.go binding) the pill takes the keyboard back on
// these delays, and losing it meanwhile isn't called a pause.
const REGAIN_MS = [30, 120, 300];
const SETTLE_MS = 500;
// How often settings.json's option_as_alt (and, for "auto", the keyboard
// layout) is read again while syncing: Herdr applies changes at once.
const OPTION_MS = 2000;
// The macOS layouts where Herdr's option_as_alt "auto" sends Option as Alt.
const ALT_LAYOUTS = ["com.apple.keylayout.US", "com.apple.keylayout.USInternational-PC", "com.apple.keylayout.ABC", "com.apple.keylayout.ABC-India"];

// Ways to start Python 3, in the order tried. On Windows `py -3` goes
// first: `python3` there may be the Store's stand-in, which opens the Store.
function pythons() {
  return window().platform === "windows" ? [["__HERDR_PYTHON__"]] : [["python3"], ["python"]];
}

// Does Option act as Alt, as it does in Herdr's terminals? macOS only:
// settings.json's option_as_alt, "on", "off" or "auto" (the default: Alt on
// the layouts above). Elsewhere Alt is always Alt.
async function optionIsAlt() {
  let mode = "auto";
  try { mode = JSON.parse(await fs.readFile(`${appHome()}/settings.json`, "utf8")).option_as_alt ?? "auto"; } catch {}
  if (mode === "on") return true;
  if (mode === "off") return false;
  const r = await exec("/usr/bin/defaults", ["read", "com.apple.HIToolbox", "AppleCurrentKeyboardLayoutInputSourceID"]);
  if (r.code !== 0) throw new Error(r.stderr || "defaults failed");
  return ALT_LAYOUTS.includes(r.stdout.trim());
}

// One key as a send.py key name, or null when it has none.
function keyName(base) {
  if (NAMED[base]) return NAMED[base];
  if (/^f([1-9]|1[0-2])$/.test(base)) return base;
  if (/^[\x21-\x7e]$/.test(base)) return base.toLowerCase();
  return null;
}

// keys.json sections that apply while the pill has the keyboard, most
// specific first.
function sections() {
  return ["mod:sync-panes", `layout:${shared("layout")}`, "global"];
}

// A binding's keys as keystrokes ("ctrl-t e" -> ["ctrl-t", "e"]).
function strokes(k) {
  return k.keys.trim().toLowerCase().split(/\s+/);
}

// Do these keystrokes begin a multi-key binding that applies, with more to
// come? ["ctrl-t"] does when "ctrl-t n" is bound.
function begins(typed) {
  const ss = sections();
  return keys().some((k) => {
    if (!ss.includes(k.section)) return false;
    const s = strokes(k);
    return s.length > typed.length && typed.every((t, i) => s[i] === t);
  });
}

// What these keystrokes do here: the most specific binding that applies.
function bindingFor(typed) {
  const want = typed.join(" ");
  for (const section of sections()) {
    const b = keys().find((k) => k.section === section && strokes(k).join(" ") === want);
    if (b) return b.action;
  }
  return null;
}

// Runs a keys.json action ("tab.next", "tab.select:2", "last-pane.go").
function runAction(action) {
  const i = action.indexOf(":");
  if (i < 0) return run(action);
  const name = action.slice(0, i), value = action.slice(i + 1);
  const arg = commands().find((c) => c.name === name)?.args[0]?.name;
  run(name, arg ? { [arg]: /^\d+$/.test(value) ? Number(value) : value } : {});
}

// A send: binding's text as input, or null when any character can't be
// typed faithfully (NUL, ctrl+\ ] ^ _, DEL): then nothing is sent. Escape
// and one printable character ("\u001bb") is Alt and that key, as a terminal
// sends it: the same bytes as the text in a plain terminal, Alt+b (not Esc,
// then b) in kitty mode. "\u001b[" and "\u001bO" start a key's own escape
// sequence, so they stay Escape and text.
function sendItems(text) {
  const out = [];
  const chars = [...text];
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i], code = ch.codePointAt(0), next = chars[i + 1];
    if (ch === "\u001b" && next && /^[\x21-\x7e]$/.test(next) && next !== "[" && next !== "O") {
      const upper = /^[A-Z]$/.test(next);
      out.push({ key: next.toLowerCase(), mods: ALT | (upper ? SHIFT : 0) });
      i++;
    } else if (ch === "\r" || ch === "\n") out.push({ key: "enter", mods: 0 });
    else if (ch === "\t") out.push({ key: "tab", mods: 0 });
    else if (ch === "\u001b") out.push({ key: "esc", mods: 0 });
    else if (code >= 1 && code <= 26) out.push({ key: String.fromCharCode(code + 96), mods: CTRL });
    else if (code < 32 || code === 127) return null;
    else out.push({ text: ch });
  }
  return out;
}

export default class SyncPanes extends View {
  init(_props, cx) {
    this.tab = focused()?.tab ?? null;
    this.queue = [];
    this.gen = 0;
    this.busy = false;
    this.pending = null;
    this.stopped = false;
    this.error = null;
    this.wasLive = false;
    this.quietUntil = 0;
    this.lastTo = null;
    this.livePane = null;
    this.liveAt = 0;
    this.pressedAt = 0;
    // Option as Alt until settings.json and the layout say otherwise.
    this.optionAlt = true;
    if (window()?.platform === "macos") {
      this.readOption(cx);
      cx.timer.every(OPTION_MS, (cx) => this.readOption(cx));
    }
    this.handle = cx.focus_handle();
    this.handle.focus();
    // One more try if the first didn't take, unless the pill has already
    // had the keyboard: then wherever it went was the person's choice.
    cx.timer.after(300, (cx) => {
      if (!this.wasLive && !this.stopped) {
        this.handle.focus();
        cx.notify();
      }
    });
    // Focus moving between the pill and a pane doesn't redraw the pill by
    // itself; redraw when it changed so Sync / Paused is never stale.
    this.shownLive = null;
    cx.timer.every(300, (cx) => {
      this.watch(cx);
      if (this.handle.is_focused() !== this.shownLive) cx.notify();
    });
    // sync-panes.stop, and sync-panes.send:<text> from a binding in the
    // mod:sync-panes section of keys.json: Herdr runs bindings itself, so a
    // plain send: would type into no terminal while the pill has the keyboard.
    cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        if (command === "stop") this.stop();
        else if (command === "paste") this.push({ paste: true }, cx);
        else if (command.startsWith("send:")) this.typeText(command.slice(5), cx);
        cx.notify();
      }
    });
  }

  // Reads option_as_alt again; on an error the last answer stays.
  readOption(cx) {
    if (this.readingOption || this.stopped) return;
    this.readingOption = true;
    cx.spawn(async () => {
      try { this.optionAlt = await optionIsAlt(); } catch {} finally { this.readingOption = false; }
    });
  }

  async close() {
    this.stopped = true;
    this.drop();
    if (this.inbox) {
      const [cmd, ...pre] = this.python;
      await exec(cmd, [...pre, "-I", "-c", "import shutil, sys; shutil.rmtree(sys.argv[1], True)", this.inbox]);
    }
  }

  // The tab's terminal panes. When a pane is zoomed, only it counts, and
  // only if it's a terminal: like tmux, panes you can't see don't get keys.
  targets() {
    const ps = panes().filter((p) => p.tab === this.tab);
    const zoomed = ps.find((p) => p.zoomed);
    if (zoomed) return zoomed.terminal ? [zoomed] : [];
    return ps.filter((p) => p.terminal);
  }

  // Forgets everything queued and any half-typed binding; sends in flight
  // see the new generation and don't go on.
  drop() {
    this.gen++;
    this.queue = [];
    this.pending = null;
  }

  // Still sending what generation `gen` queued?
  alive(gen) {
    return !this.stopped && gen === this.gen && focused()?.tab === this.tab;
  }

  // Leaving the tab stops; losing the keyboard or a change in the target
  // panes drops what's queued. Runs on a timer and on every render.
  //
  // Herdr runs keys.json bindings itself, so a pane.go binding moves
  // the keyboard to a pane without the pill seeing a key. Losing it with no
  // press outside the pill since it last had it, to another pane of the
  // tab, is such a move: the pill takes the keyboard back and keeps
  // syncing, as tmux does. A click (or a dialog, which leaves the pane as
  // it was) pauses.
  watch(cx) {
    if (this.stopped) return;
    const tab = focused()?.tab;
    if (tab && tab !== this.tab) return this.stop();
    const pane = focused()?.pane;
    if (this.handle.is_focused()) {
      this.wasLive = true;
      this.livePane = pane;
      this.liveAt = Date.now();
    } else if (this.wasLive && Date.now() > this.quietUntil) {
      const moved = this.pressedAt < this.liveAt && pane !== this.livePane && this.targets().some((p) => p.pane === pane);
      if (moved && cx) {
        this.livePane = pane;
        this.regain(cx);
      } else if (!moved) {
        this.wasLive = false;
        this.drop();
      }
    }
    const to = this.targets().map((p) => p.terminal).join(" ");
    if (this.lastTo !== null && to !== this.lastTo) this.drop();
    this.lastTo = to;
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.drop();
    closeOverlay(props().overlay);
  }

  // A KeyEvent as input: { key, mods }, { text }, or null. What a key
  // types without Ctrl or Alt (letters, symbols, Japanese) goes as text.
  // When Option isn't Alt (option_as_alt), what Option types on a character
  // key goes as text too, as in Herdr's terminals: Option+¥ is "\" on JIS.
  translate(e) {
    const m = e.modifiers;
    const base = e.key;
    const named = NAMED[base] || /^f([1-9]|1[0-2])$/.test(base);
    if (m.alt && !m.control && !named && !this.optionAlt) {
      return e.key_char ? { text: e.key_char } : null;
    }
    const mods = (m.shift ? SHIFT : 0) | (m.alt ? ALT : 0) | (m.control ? CTRL : 0);
    if (m.control || m.alt || named) {
      const name = keyName(base);
      return name ? { key: name, mods } : null;
    }
    const ch = e.key_char;
    return ch ? { text: ch } : null;
  }

  key(e, cx) {
    cx.stop_propagation();
    if (this.stopped) return;
    const stroke = e.keystroke.toLowerCase();
    // The keys of a multi-key binding are held, not typed, until they make
    // up a whole binding or can't any more.
    if (this.pending) {
      const typed = [...this.pending, stroke];
      this.pending = null;
      if (stroke === "escape") return;
      if (begins(typed)) {
        this.pending = typed;
        return;
      }
      return this.sequence(typed, cx);
    }
    if (begins([stroke])) {
      this.pending = [stroke];
      return;
    }
    // After a failure nothing is typed until the pill is clicked.
    if (this.error) return;
    if (e.modifiers.platform) {
      if (e.key === "v") this.push({ paste: true }, cx);
      return;
    }
    const input = this.translate(e);
    if (input) this.push({ input: [input] }, cx);
  }

  // The keys of a multi-key binding: that binding, as tmux runs its command
  // instead of sending the keys. Keys that match no binding do nothing, and
  // neither does `terminal` (it means "let the program have the key", and
  // there's no program here).
  sequence(typed, cx) {
    const action = bindingFor(typed);
    if (!action || action === "terminal") return;
    // Opening it again closes it, as Herdr's mod.open does.
    if (action === "sync-panes.stop" || action.startsWith("mod.open:sync-panes")) return this.stop();
    if (action.startsWith("send:")) return this.typeText(action.slice(5), cx);
    // Moving between panes keeps syncing, as in tmux; an action that opens
    // a dialog leaves the focused pane as it was and keeps the keyboard.
    const before = focused()?.pane;
    runAction(action);
    this.regain(cx, before);
  }

  // A send: binding's text, typed into every terminal.
  typeText(text, cx) {
    if (this.stopped || this.error) return;
    const items = sendItems(text);
    if (!items) return notify({ title: LABEL.failedTitle, body: LABEL.badSend, level: "warning" });
    this.push({ input: items }, cx);
  }

  // Takes the keyboard back once Herdr has moved focus, if the pill had it,
  // the tab is the same and (with `before`) the focused pane changed.
  regain(cx, before) {
    this.quietUntil = Date.now() + SETTLE_MS;
    for (const ms of REGAIN_MS) {
      cx.timer.after(ms, (cx) => {
        if (this.stopped || this.handle.is_focused() || focused()?.tab !== this.tab) return;
        if (before !== undefined && focused()?.pane === before) return;
        this.handle.focus();
        cx.notify();
      });
    }
  }

  // Queues an item for the panes there are now, merging its input into the
  // last item's when that goes to the same panes and has room.
  push(item, cx) {
    // Catch up first, so a change in panes drops older items, not this one.
    this.watch(cx);
    if (this.stopped) return;
    const targets = this.targets();
    if (!targets.length) return;
    item.targets = targets;
    item.to = targets.map((p) => p.terminal).join(" ");
    item.gen = this.gen;
    const last = this.queue[this.queue.length - 1];
    if (last && last.to === item.to && last.input && item.input && last.input.length + item.input.length <= BATCH) {
      for (const input of item.input) {
        const end = last.input[last.input.length - 1];
        if (end?.text != null && input.text != null) end.text += input.text;
        else last.input.push(input);
      }
    } else this.queue.push(item);
    this.drain(cx);
  }

  drain(cx) {
    if (this.busy) return;
    this.busy = true;
    cx.spawn(async (cx) => {
      try {
        while (this.queue.length && !this.stopped) {
          this.watch(cx);
          const item = this.queue.shift();
          if (!item || !this.alive(item.gen)) continue;
          if (item.paste) this.pasteEach(item.targets, cx);
          else await this.send(item.targets, item.input);
        }
      } catch (err) {
        this.fail([], String(err?.message ?? err));
      } finally {
        this.busy = false;
        cx.notify();
      }
    });
  }

  // Stops typing: what's queued is dropped (a trailing Enter must not run a
  // half-typed command anywhere) and input waits for a click on the pill.
  fail(terminals, message) {
    this.drop();
    this.error = { terminals, message: message || "send failed" };
    notify({ title: LABEL.failedTitle, body: `${terminals.join(", ")} ${this.error.message}`.trim(), level: "error" });
  }

  // One send.py run types the input into every target and reports each
  // one, failed or not, before the next batch goes. What's typed travels in
  // a file in a folder only this user can open (send.py deletes it), never
  // in arguments, which other users can see in `ps`: synced typing is often
  // a password.
  async send(targets, input) {
    const terminals = targets.map((p) => p.terminal);
    if (!this.inbox) {
      // The first Python that runs (-I rules out Python 2) makes the folder.
      for (const [cmd, ...pre] of pythons()) {
        const m = await exec(cmd, [...pre, "-I", "-c", "import tempfile; print(tempfile.mkdtemp(prefix='sync-panes-'))"]).catch(() => null);
        if (m?.code !== 0 || !m.stdout.trim()) continue;
        this.python = [cmd, ...pre];
        this.inbox = m.stdout.trim();
        break;
      }
      if (!this.inbox) return this.fail(terminals, LABEL.noPython);
    }
    const file = `${this.inbox}/${this.sends = (this.sends ?? 0) + 1}.json`;
    await writeTextFile(file, JSON.stringify({ terminals, input }), null);
    const [cmd, ...pre] = this.python;
    const r = await exec(cmd, [...pre, "-I", `${appHome()}/mods/sync-panes/send.py`, file]);
    let report = null;
    try { report = JSON.parse(r.stdout); } catch {}
    if (r.code !== 0 || !report) return this.fail(terminals, (r.stderr || r.stdout).trim().split("\n").pop() || `send.py exited ${r.code}`);
    const bad = terminals.filter((t) => report[t] !== null);
    if (bad.length) this.fail(bad, report[bad[0]]);
  }

  // Pastes into each pane in turn; run() doesn't report whether a paste
  // landed. Focus goes back to where it was, and the pill gets the keyboard
  // back only if it had it.
  pasteEach(targets, cx) {
    const back = focused()?.pane;
    const live = this.handle.is_focused();
    this.quietUntil = Date.now() + SETTLE_MS;
    try {
      for (const p of targets) {
        run("pane.focus", { pane: p.pane });
        run("terminal.paste");
      }
    } finally {
      if (back) run("pane.focus", { pane: back });
      if (live) {
        this.handle.focus();
        if (cx) this.regain(cx);
      }
    }
  }

  resume() {
    this.error = null;
    this.pending = null;
    this.handle.focus();
  }

  // A small pill: it has to hold the keyboard, so it can't go away, but it
  // stays out of the way. Drag it anywhere; the window remembers the spot.
  render(cx) {
    this.watch(cx);
    const t = theme();
    const n = this.targets().length;
    const live = this.handle.is_focused();
    this.shownLive = live;
    const name = spaces().flatMap((s) => s.tabs).find((x) => x.id === this.tab)?.name ?? "";
    const color = this.error ? t.blocked : live && n ? t.accent : t.dim;
    const text = this.error ? LABEL.failed(this.error.terminals.join(", ") || "")
      : !n ? LABEL.none
      : live ? LABEL.sync(n, name)
      : LABEL.paused;
    return h_flex().id("sync-panes").track_focus(this.handle).on_key_down((e, cx) => this.key(e, cx))
      .on_click((_e, cx) => { this.resume(); cx.notify(); })
      .on_mouse_down_out(() => { this.pressedAt = Date.now(); })
      .h(24).pl(10).pr(4).gap(6).items_center().rounded(12)
      .bg(t.popover).border_1().border_color(color).text_size(11.5).text_color(t.foreground)
      .child(div().w(6).h(6).rounded(3).bg(color)
        .when(live && n > 0 && !this.error, (el) => el.loop("opacity", { from: 0.35, to: 1, period: 1200 })))
      .child(div().text_color(live || this.error ? t.foreground : t.muted).child(text))
      .child(div().id("bc-close").w(18).h(18).rounded(9).flex().items_center().justify_center()
        .text_size(10).text_color(t.dim).cursor_pointer()
        .hover((s) => s.bg(t.hover).text_color(t.foreground))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click(() => this.stop()).child("✕"));
  }
}
