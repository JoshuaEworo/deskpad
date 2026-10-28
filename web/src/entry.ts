import "./style.css";
import { enrollment } from "./enrollment";

async function open() {
  if (await enrollment()) return;
  const pairing = location.hash.startsWith("#deskpad=");
  const remembered = localStorage.getItem("deskpad.remote");
  const connect =
    new URLSearchParams(location.search).has("connect") ||
    matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone;
  if (!pairing && !remembered && !connect) {
    try {
      const response = await fetch("/api/status");
      if ((await response.json()).remoteService) {
        const { landing } = await import("./landing");
        landing();
        return;
      }
    } catch {
      /* Local hosts retain their existing pairing flow. */
    }
  }
  await import("./main");
}
void open().catch(() => {
  document.getElementById("app")!.textContent =
    "This setup link is invalid. Open Deskpad on your laptop and try again.";
});
