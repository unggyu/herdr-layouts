import { View, div } from "gpui-kit";
import { exec, appHome, notify, window } from "herdr";

export default class SessionRestore extends View {
  init(_props, cx) {
    // Deferred so `herdr-app check` doesn't start a background service.
    cx.timer.after(500, (cx) => {
      if (window()?.platform !== "windows") return;
      cx.spawn(async () => {
        try {
          const result = await exec("__WINDOWS_ROOT__/System32/WindowsPowerShell/v1.0/powershell.exe",
            ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
             `${appHome()}/mods/session-restore/start.ps1`]);
          if (result.code !== 0) throw new Error(result.stderr || result.stdout);
        } catch (error) {
          notify({ title: "Session recovery", body: String(error?.message ?? error), level: "error" });
        }
      });
    });
  }
  render() { return div(); }
}
