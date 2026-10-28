import "./style.css";
import { enrollment } from "./enrollment";
void enrollment()
  .then((active) => {
    if (!active) void import("./main");
  })
  .catch(() => {
    const root = document.getElementById("app")!;
    root.textContent =
      "This setup link is invalid. Open Deskpad on your laptop and try again.";
  });
