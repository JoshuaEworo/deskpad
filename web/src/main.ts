import "./style.css";
import { Connection } from "./connection";
import { TrackpadGesture } from "./gestures";
import { attachKeyboard } from "./keyboard";
import type { Frame } from "./protocol";

const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const typing = $<HTMLTextAreaElement>("typing");
const desktop = $<HTMLImageElement>("desktop");
const pad = $("trackpad");
let toastTimer: ReturnType<typeof setTimeout>;
function toast(message: string) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 4500);
}
let frame: Frame | undefined,
  imageUrl = "",
  position: [number, number] = [0, 0];
let desiredConnection = false;
const modifiers = new Set<string>();
let dragLocked = false;

function drawCursor() {
  if (!frame) return;
  const b = frame.bounds,
    x = (position[0] - b.left) / b.width,
    y = (position[1] - b.top) / b.height;
  const cursor = $("cursor");
  cursor.hidden = x < 0 || x > 1 || y < 0 || y > 1;
  cursor.style.left = `${x * 100}%`;
  cursor.style.top = `${y * 100}%`;
}

function clearVisualInputs() {
  modifiers.clear();
  dragLocked = false;
  document
    .querySelectorAll("[data-mod]")
    .forEach((el) => el.setAttribute("aria-pressed", "false"));
  $("drag-lock").setAttribute("aria-pressed", "false");
}

const connection = new Connection({
  state(state) {
    const labels = {
      connecting: "Connecting…",
      connected: "Connected to laptop",
      disconnected: "Reconnecting…",
      paused: "Disconnected",
      busy: "Laptop is in use",
      unpaired: "Pair this phone",
    };
    $("status").textContent = labels[state];
    $("status-dot").classList.toggle("live", state === "connected");
    if (state !== "connected") {
      clearVisualInputs();
      gesture.cancel();
    }
    if (state === "unpaired") {
      $("workspace").hidden = true;
      $("pairing").hidden = false;
    }
    if (state === "busy")
      toast(
        "Another tab or phone is controlling the laptop. Disconnect it first.",
      );
  },
  async frame(blob, metadata) {
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.src = url;
    try {
      await image.decode();
    } catch (error) {
      URL.revokeObjectURL(url);
      throw error;
    }
    desktop.src = url;
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    imageUrl = url;
    frame = metadata;
    position = metadata.cursor;
    const screen = $("screen");
    const ratio = metadata.width / metadata.height;
    const w = Math.min(screen.clientWidth, screen.clientHeight * ratio);
    $("picture").style.width = `${w}px`;
    $("screen-empty").hidden = true;
    drawCursor();
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => resolve()),
    );
  },
  cursor(value) {
    position = value;
    drawCursor();
  },
  latency(ms) {
    $("metrics").textContent = `${Math.round(ms)} MS · LOCAL`;
  },
  error: toast,
});
const gesture = new TrackpadGesture((message) => {
  // Drag lock owns the held button until explicitly released.
  if (dragLocked && message.type === "button") return;
  connection.send(message);
});

const storedSpeed = Number(localStorage.getItem("deskpad.speed") || 1.5);
gesture.speed = Number.isFinite(storedSpeed)
  ? Math.max(0.5, Math.min(4, storedSpeed))
  : 1.5;
$<HTMLInputElement>("sensitivity").value = String(gesture.speed);
$("speed-value").textContent = `${gesture.speed.toFixed(1)}×`;
gesture.natural = localStorage.getItem("deskpad.natural") !== "false";
$<HTMLInputElement>("natural-scroll").checked = gesture.natural;
$("sensitivity").addEventListener("input", (event) => {
  gesture.speed = Number((event.target as HTMLInputElement).value);
  $("speed-value").textContent = `${gesture.speed.toFixed(1)}×`;
  localStorage.setItem("deskpad.speed", String(gesture.speed));
});
$("natural-scroll").addEventListener("change", (event) => {
  gesture.natural = (event.target as HTMLInputElement).checked;
  localStorage.setItem("deskpad.natural", String(gesture.natural));
});

let holdTimer: ReturnType<typeof setTimeout>;
const padContacts = new Set<number>();
pad.addEventListener("pointerdown", (event) => {
  padContacts.add(event.pointerId);
  event.preventDefault();
  pad.setPointerCapture(event.pointerId);
  pad.classList.add("engaged");
  gesture.down(
    event.pointerId,
    event.clientX,
    event.clientY,
    performance.now(),
  );
  clearTimeout(holdTimer);
  holdTimer = setTimeout(() => gesture.hold(performance.now()), 365);
});
pad.addEventListener("pointermove", (event) => {
  if (pad.hasPointerCapture(event.pointerId))
    gesture.move(event.pointerId, event.clientX, event.clientY);
});
pad.addEventListener("pointerup", (event) => {
  padContacts.delete(event.pointerId);
  gesture.up(event.pointerId, performance.now());
  pad.classList.remove("engaged");
  clearTimeout(holdTimer);
});
pad.addEventListener("pointercancel", () => {
  padContacts.clear();
  gesture.cancel();
  pad.classList.remove("engaged");
  clearTimeout(holdTimer);
});
pad.addEventListener("lostpointercapture", (event) => {
  if (!padContacts.has(event.pointerId)) return;
  padContacts.clear();
  gesture.cancel();
  pad.classList.remove("engaged");
  clearTimeout(holdTimer);
});
pad.addEventListener("contextmenu", (event) => event.preventDefault());

function clearModifiers() {
  for (const key of modifiers)
    connection.send({ type: "key", key, action: "up" });
  modifiers.clear();
  document
    .querySelectorAll("[data-mod]")
    .forEach((el) => el.setAttribute("aria-pressed", "false"));
}
function sendKey(key: string) {
  connection.send({ type: "key", key, action: "press" });
  clearModifiers();
}
function sendText(value: string) {
  if (
    modifiers.has("Control") ||
    modifiers.has("Alt") ||
    modifiers.has("Meta")
  ) {
    if (/^[a-z]$/i.test(value)) sendKey(value.toLowerCase());
    else {
      toast("Use a single letter with Ctrl, Alt, or Windows.");
      clearModifiers();
    }
    return;
  }
  if (modifiers.has("Shift")) value = value.toUpperCase();
  // Chunk by code points so a Unicode surrogate pair is never split.
  const chars = Array.from(value);
  for (let i = 0; i < chars.length; i += 512)
    connection.send({ type: "text", text: chars.slice(i, i + 512).join("") });
  clearModifiers();
}
attachKeyboard(typing, sendText, sendKey);
document
  .querySelectorAll<HTMLButtonElement>("[data-key]")
  .forEach((button) =>
    button.addEventListener("click", () => sendKey(button.dataset.key!)),
  );
document.querySelectorAll<HTMLButtonElement>("[data-mod]").forEach((button) =>
  button.addEventListener("click", () => {
    const key = button.dataset.mod!;
    const down = !modifiers.has(key);
    connection.send({ type: "key", key, action: down ? "down" : "up" });
    if (down) modifiers.add(key);
    else modifiers.delete(key);
    button.setAttribute("aria-pressed", String(down));
  }),
);
document
  .querySelectorAll<HTMLButtonElement>("[data-shortcut]")
  .forEach((button) =>
    button.addEventListener("click", () => {
      clearModifiers();
      connection.send({
        type: "shortcut",
        keys: button.dataset.shortcut!.split(","),
      });
    }),
  );

for (const [id, button] of [
  ["mouse-left", "left"],
  ["mouse-right", "right"],
] as const) {
  $(id).addEventListener("pointerdown", (event) => {
    event.preventDefault();
    $(id).setPointerCapture(event.pointerId);
    if (dragLocked && button === "left") return;
    connection.send({ type: "button", button, action: "down" });
  });
  for (const kind of ["pointerup", "pointercancel", "lostpointercapture"])
    $(id).addEventListener(kind, () => {
      if (!(dragLocked && button === "left"))
        connection.send({ type: "button", button, action: "up" });
    });
}
$("drag-lock").addEventListener("click", () => {
  gesture.cancel();
  dragLocked = !dragLocked;
  connection.send({
    type: "button",
    button: "left",
    action: dragLocked ? "down" : "up",
  });
  $("drag-lock").setAttribute("aria-pressed", String(dragLocked));
});

function keyboard(open: boolean) {
  $("typing-row").hidden = !open;
  $("keyboard-toggle").setAttribute("aria-expanded", String(open));
  if (open) typing.focus({ preventScroll: true });
  else typing.blur();
}
$("keyboard-toggle").addEventListener("click", () =>
  keyboard($("typing-row").hidden),
);
$("hide-keyboard").addEventListener("click", () => keyboard(false));
// Keep native keyboard focus while operating desktop keys or the trackpad.
document
  .querySelectorAll(".key-strip button,.mouse-row button,.shortcuts button")
  .forEach((button) =>
    button.addEventListener("pointerdown", (event) => event.preventDefault()),
  );
$("shortcuts-toggle").addEventListener("click", () => {
  $("shortcuts").hidden = !$("shortcuts").hidden;
  $("shortcuts-toggle").setAttribute(
    "aria-expanded",
    String(!$("shortcuts").hidden),
  );
});
$("paste-text").addEventListener("click", () => {
  keyboard(false);
  $<HTMLDialogElement>("text-dialog").showModal();
});
$<HTMLDialogElement>("text-dialog").addEventListener("close", () => {
  if ($<HTMLDialogElement>("text-dialog").returnValue === "send") {
    clearModifiers();
    const field = $<HTMLTextAreaElement>("paste-content");
    if (field.value) sendText(field.value);
    field.value = "";
  }
});

let size = Number(localStorage.getItem("deskpad.screen") || 38);
if (!Number.isFinite(size)) size = 38;
function resizeScreen(value: number) {
  size = Math.max(22, Math.min(65, value));
  document.documentElement.style.setProperty("--screen", `${size}%`);
  $("divider").setAttribute("aria-valuenow", String(Math.round(size)));
  localStorage.setItem("deskpad.screen", String(size));
}
resizeScreen(size);
$("divider").addEventListener("pointerdown", (event) => {
  event.preventDefault();
  $("divider").setPointerCapture(event.pointerId);
});
$("divider").addEventListener("pointermove", (event) => {
  if (!$("divider").hasPointerCapture(event.pointerId)) return;
  const workspace = $("workspace").getBoundingClientRect(),
    screen = $("screen").getBoundingClientRect();
  resizeScreen(((event.clientY - screen.top) / workspace.height) * 100);
});
$("divider").addEventListener("keydown", (event) => {
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    resizeScreen(size + (event.key === "ArrowUp" ? -3 : 3));
  }
});

// Screen gestures transform only the viewer; they never move the Windows cursor.
const contacts = new Map<number, { x: number; y: number }>();
let zoom = 1,
  panX = 0,
  panY = 0;
function transform() {
  const stage = $("screen");
  panX = Math.max(
    (-stage.clientWidth * (zoom - 1)) / 2,
    Math.min((stage.clientWidth * (zoom - 1)) / 2, panX),
  );
  panY = Math.max(
    (-stage.clientHeight * (zoom - 1)) / 2,
    Math.min((stage.clientHeight * (zoom - 1)) / 2, panY),
  );
  $("picture").style.transform =
    `translate(${panX}px,${panY}px) scale(${zoom})`;
}
const distance = () => {
  const p = [...contacts.values()];
  return p.length === 2 ? Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) : 0;
};
$("screen").addEventListener("pointerdown", (event) => {
  if ((event.target as HTMLElement).closest("button")) return;
  event.preventDefault();
  $("screen").setPointerCapture(event.pointerId);
  contacts.set(event.pointerId, { x: event.clientX, y: event.clientY });
});
$("screen").addEventListener("pointermove", (event) => {
  const old = contacts.get(event.pointerId);
  if (!old) return;
  const before = distance();
  const dx = event.clientX - old.x,
    dy = event.clientY - old.y;
  contacts.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (contacts.size === 2 && before > 0)
    zoom = Math.max(1, Math.min(4, (zoom * distance()) / before));
  else if (zoom > 1) {
    panX += dx;
    panY += dy;
  }
  transform();
});
for (const event of ["pointerup", "pointercancel"])
  $("screen").addEventListener(event, (event) =>
    contacts.delete((event as PointerEvent).pointerId),
  );
$("reset-view").addEventListener("click", () => {
  zoom = 1;
  panX = panY = 0;
  transform();
});

// iOS shrinks VisualViewport when the native keyboard opens, not always the layout viewport.
function viewport() {
  const v = window.visualViewport;
  document.documentElement.style.setProperty(
    "--app-height",
    `${v?.height ?? innerHeight}px`,
  );
  document.documentElement.style.setProperty(
    "--app-offset",
    `${v?.offsetTop ?? 0}px`,
  );
}
window.visualViewport?.addEventListener("resize", viewport);
window.visualViewport?.addEventListener("scroll", viewport);
window.addEventListener("resize", viewport);
viewport();
function releaseInputs() {
  gesture.cancel();
  clearVisualInputs();
  connection.release();
}
window.addEventListener("blur", releaseInputs);
window.addEventListener("pagehide", () => connection.stop());
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    releaseInputs();
    connection.stop();
  } else if (desiredConnection) connection.start();
});
$("settings-toggle").addEventListener("click", () => {
  releaseInputs();
  $("settings").hidden = !$("settings").hidden;
});
$("settings-close").addEventListener(
  "click",
  () => ($("settings").hidden = true),
);
$("disconnect").addEventListener("click", () => {
  desiredConnection = false;
  connection.stop();
  $("settings").hidden = true;
});
$("reconnect").addEventListener("click", () => {
  desiredConnection = true;
  connection.start();
});
$("forget").addEventListener("click", async () => {
  desiredConnection = false;
  connection.stop();
  const result = await fetch("/api/forget", { method: "POST" });
  if (!result.ok) {
    toast("Could not forget this phone. Check the host.");
    return;
  }
  $("settings").hidden = true;
  $("workspace").hidden = true;
  $("pairing").hidden = false;
});

function enterWorkspace(demo: boolean) {
  $("pairing").hidden = true;
  $("workspace").hidden = false;
  $("pad-hint").textContent = demo
    ? "Demo · no real computer input"
    : "Two fingers to scroll";
  desiredConnection = true;
  connection.start();
}
$("pair-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("pair-error").textContent = "";
  const button =
    document.querySelector<HTMLButtonElement>("#pair-form button")!;
  button.disabled = true;
  try {
    const response = await fetch("/api/pair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $<HTMLInputElement>("pair-code").value }),
    });
    const body = await response.json();
    if (!response.ok)
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : "Enter the six-digit host code.",
      );
    $<HTMLInputElement>("pair-code").blur();
    const status = await (await fetch("/api/status")).json();
    enterWorkspace(status.demo);
  } catch (error) {
    $("pair-error").textContent =
      error instanceof Error ? error.message : "Could not connect.";
  } finally {
    button.disabled = false;
  }
});
void fetch("/api/status")
  .then((r) => r.json())
  .then((status) => {
    if (status.paired) enterWorkspace(status.demo);
    else $("pairing").hidden = false;
  })
  .catch(() => {
    $("pairing").hidden = false;
    $("pair-error").textContent =
      "Cannot reach the host. Keep Deskpad running on your laptop, then reload.";
  });
