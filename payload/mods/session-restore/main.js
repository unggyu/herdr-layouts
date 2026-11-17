import { View, div } from "gpui-kit";
import { exec, appHome, notify, window, checking, nextCommand, openOverlay } from "herdr";

export default class SessionRestore extends View {
  init(_props, cx) {
    if(checking()) return;
    cx.spawn(async()=>{for(;;){const c=await nextCommand();if(c.startsWith("history:"))openOverlay({mod:"session-history",kind:"dialog",width:1000,height:680,props:{terminal:c.slice(8)}});}});
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
