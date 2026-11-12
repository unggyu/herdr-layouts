import { View, div } from "gpui-kit";
import { nextCommand, focused, exec, appHome, run, notify } from "herdr";
export default class WslClipboard extends View {
  init(_props, cx) {
    this.busy = false;
    cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        if (command.startsWith("copy-id:")) {
          const terminal = command.slice(8);
          try {
            const r = await exec("__WINDOWS_ROOT__/System32/WindowsPowerShell/v1.0/powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", "Set-Clipboard -Value '" + terminal.replace(/'/g, "''") + "'"]);
            if (r.code !== 0) throw new Error(r.stderr || r.stdout || "Clipboard copy failed");
            notify({title: "터미널 ID 복사", body: terminal});
          } catch (error) {
            notify({title: "터미널 ID 복사 실패", body: String(error?.message ?? error), level: "error"});
          }
          continue;
        }
        const reveal = command === "reveal" || command.startsWith("reveal:");
        const open = command === "open" || command.startsWith("open:");
        const fileAction = reveal || open;
        if ((!fileAction && command !== "paste") || this.busy) continue;
        const target = command.startsWith("reveal:") ? command.slice(7) : command.startsWith("open:") ? command.slice(5) : focused()?.terminal;
        if (!target) continue;
        this.busy = true;
        try {
          if (fileAction) {
            run("pane.focus", { terminal: target });
            run("terminal.copy");
          }
          const script = fileAction ? "open_path.py" : "paste.py";
          const actionArgs = open ? ["--action", "open"] : [];
          const r = await exec("__HERDR_PYTHON__", ["-I", `${appHome()}/mods/wsl-clipboard/${script}`, target, ...actionArgs]);
          let result;
          try { result = JSON.parse(r.stdout); } catch { throw new Error(r.stderr || r.stdout || "Clipboard bridge failed"); }
          if (r.code !== 0 || result.error) throw new Error(result.error || r.stderr);
          if (result.kind === "text" && focused()?.terminal === target) run("terminal.paste");
        } catch (error) {
          notify({title:fileAction ? "파일 열기" : "Image paste failed", body:String(error?.message ?? error), level:"error"});
        } finally { this.busy = false; }
        cx.notify();
      }
    });
  }
  render() { return div(); }
}
