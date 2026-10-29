import "./style.css";
import { Connection } from "./session";
import { TrackpadGesture } from "./gestures";
import { attachKeyboard } from "./keyboard";
import type { Frame } from "./protocol";
import { DesktopViewer } from "./viewer";
import { attachTrackpadSurface } from "./trackpad-surface";

const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const typing = $("typing");
const desktop = $<HTMLImageElement>("desktop");
const desktopVideo = $<HTMLVideoElement>("desktop-video");
const laptopAudio = $<HTMLAudioElement>("laptop-audio");
let route = "Local";
let cameraFacing: "user" | "environment" = "user";
const pad = $("trackpad");
const viewer = new DesktopViewer($("screen"), $("picture"));
let landscape = false;
let controlMode: "mouse" | "view" = "mouse";
let portraitKeyboard = false;
let dockCollapsed = localStorage.getItem("deskpad.dockCollapsed") === "true";
let keyboardWanted = false;
let restoreKeyboard = false;
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

let displayPreferencesApplied = false;
let displaySignature = "";
let activeDisplay: number | undefined;
let monitorKeyboardRestore = false;
function updateDisplays(metadata: Frame) {
  const displays = metadata.displays;
  if (!displays?.length) return;
  const multiple = displays.length > 1;
  $("display-control").hidden = !multiple;
  const selector = $<HTMLSelectElement>("monitor-switch");
  const signature = JSON.stringify(
    displays.map((d) => [d.id, d.width, d.height]),
  );
  if (signature !== displaySignature) {
    displaySignature = signature;
    selector.replaceChildren(
      ...displays.map((display) => {
        const option = new Option(String(display.id), String(display.id));
        option.setAttribute(
          "aria-label",
          `${display.name}, ${display.width} by ${display.height}`,
        );
        return option;
      }),
    );
  }
  if (activeDisplay !== undefined && activeDisplay !== metadata.monitor)
    viewer.reset();
  activeDisplay = metadata.monitor;
  selector.value = String(metadata.monitor);
  selector.title = `Display ${metadata.monitor} of ${displays.length}`;
  $("display-details").textContent =
    `${displays.length} ${multiple ? "displays" : "display"} detected. Viewing Display ${metadata.monitor}.`;
  const follow = $<HTMLInputElement>("follow-cursor");
  follow.disabled = !multiple;
  const preferred = localStorage.getItem("deskpad.followCursor");
  follow.checked =
    preferred === null ? metadata.followCursor !== false : preferred === "true";
  if (!displayPreferencesApplied) {
    displayPreferencesApplied = true;
    if (preferred !== null && (preferred === "true") !== metadata.followCursor)
      connection.send({ type: "display", follow_cursor: preferred === "true" });
  }
}

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

function showEnded(reason: "revoked" | "ended") {
  if (reason === "ended")
    sessionStorage.setItem("deskpad.sessionEnded", "true");
  else sessionStorage.removeItem("deskpad.sessionEnded");
  desiredConnection = false;
  desktopVideo.srcObject = null;
  laptopAudio.srcObject = null;
  desktop.removeAttribute("src");
  frame = undefined;
  $("screen-empty").hidden = false;
  $("cursor").hidden = true;
  $("workspace").hidden = true;
  $("pairing").hidden = false;
  $("app").classList.remove("in-session");
  closeSettings(false);
  keyboard(false);
  $("remote-pair").hidden = true;
  $("session-resume").hidden = reason !== "ended";
  $("pair-form").hidden = reason === "ended" || !!connection.remote;
  $("pair-title").textContent =
    reason === "revoked" ? "Access removed" : "Session ended";
  $("local-pair-description").hidden = false;
  $("local-pair-description").textContent =
    reason === "ended"
      ? "Your phone is still paired. Reconnect when you’re ready."
      : connection.remote
        ? "Scan a new QR code on your laptop to pair again."
        : "Enter the new pairing code shown on your laptop.";
  $("scan-qr").hidden = reason !== "revoked" || !connection.remote;
  $("pair-note").textContent = "Your laptop controls who can connect.";
}

const connection = new Connection({
  progress(message) {
    $("remote-pair-status").textContent = message;
    $("screen-empty").textContent = message;
    $("connection-detail").textContent = message;
  },
  ended: showEnded,
  state(state) {
    if (state !== "connected") displayPreferencesApplied = false;
    $<HTMLSelectElement>("monitor-switch").disabled = state !== "connected";
    $<HTMLButtonElement>("remote-connect").disabled = state === "connecting";
    const labels = {
      connecting: "Connecting…",
      connected: "Connected to laptop",
      disconnected: "Reconnecting…",
      paused: "Disconnected",
      busy: "Laptop is in use",
      unpaired: "Pair this phone",
    };
    if (state === "connected") {
      $("pairing").hidden = true;
      $("workspace").hidden = false;
      $("app").classList.add("in-session");
    } else {
      $("screen-empty").hidden = false;
      desktopVideo.srcObject = null;
      laptopAudio.srcObject = null;
      $("cursor").hidden = true;
      for (const id of ["phone-camera", "phone-microphone", "phone-speaker"])
        $<HTMLInputElement>(id).checked = false;
    }
    $("status").textContent = labels[state];
    $("connection-detail").textContent = labels[state];
    $("brand-status").title = labels[state];
    $("brand-status").setAttribute("aria-label", `Deskpad: ${labels[state]}`);
    $("status-dot").classList.toggle("live", state === "connected");
    $("rail-status-dot").classList.toggle("live", state === "connected");
    $("rail-brand").title = labels[state];
    if (state !== "connected") {
      clearVisualInputs();
      gesture.cancel();
    }
    if (state === "unpaired") {
      $("workspace").hidden = true;
      $("pairing").hidden = false;
      $("app").classList.remove("in-session");
      keyboard(false);
    }
    if (state === "busy")
      toast(
        "Another tab or phone is controlling the laptop. Disconnect it first.",
      );
  },
  async frame(blob, metadata) {
    updateDisplays(metadata);
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.src = url;
    try {
      await image.decode();
    } catch (error) {
      URL.revokeObjectURL(url);
      throw error;
    }
    desktopVideo.hidden = true;
    desktop.hidden = false;
    desktop.src = url;
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    imageUrl = url;
    frame = metadata;
    position = metadata.cursor;
    viewer.setAspect(metadata.width, metadata.height);
    $("screen-empty").hidden = true;
    drawCursor();
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => resolve()),
    );
  },
  mediaAllowed(allowed) {
    for (const [id, name, value] of [
      ["phone-camera", "camera", allowed.camera],
      ["phone-microphone", "microphone", allowed.microphone],
      ["phone-speaker", "speakers", allowed.speakers],
    ] as const) {
      const secure = name === "speakers" || window.isSecureContext;
      $<HTMLInputElement>(id).disabled = !value || !secure;
      const setup = allowed.setup?.[name];
      const detail = !secure
        ? "Use Anywhere mode on your laptop and scan its secure QR link to enable phone camera and microphone."
        : value
          ? setup?.detail || "Ready. Turn this on to start."
          : setup && !setup.ready
            ? `${setup.state} on laptop. ${setup.detail} Open Deskpad Settings on your laptop.`
            : "Enable this feature in Deskpad Settings on your laptop and save.";
      $(id).title = detail;
      $(`${id}-help`).textContent = detail;
    }
  },
  mediaError(kind, error) {
    const name =
      kind === "video" ? "camera" : kind === "audio" ? "microphone" : undefined;
    if (name) {
      $<HTMLInputElement>(`phone-${name}`).checked = false;
      void connection.media(name, false);
    }
    if (kind === "speakers") {
      $<HTMLInputElement>("phone-speaker").checked = false;
      connection.listen(false);
      laptopAudio.pause();
    }
    toast(error);
  },
  localCamera(stream) {
    const preview = $<HTMLVideoElement>("camera-preview");
    preview.srcObject = stream;
    preview.hidden = !stream;
    if (stream) void preview.play().catch(() => {});
  },
  metadata(metadata) {
    updateDisplays(metadata);
    frame = metadata;
    position = metadata.cursor;
    viewer.setAspect(metadata.width, metadata.height);
    $("screen-empty").hidden = true;
    drawCursor();
  },
  stream(stream, kind) {
    if (kind === "video") {
      desktop.hidden = true;
      desktopVideo.hidden = false;
      desktopVideo.srcObject = stream;
      void desktopVideo
        .play()
        .catch(() => toast("Tap Reconnect to resume desktop video."));
    } else {
      laptopAudio.srcObject = stream;
      if ($<HTMLInputElement>("phone-speaker").checked)
        void laptopAudio
          .play()
          .catch(() => toast("Tap Hear laptop audio to start playback."));
    }
  },
  route(value) {
    route = value;
  },
  pairing(code) {
    $("remote-pair-status").textContent =
      `Approve this code on your laptop: ${code}`;
  },
  cursor(value) {
    position = value;
    drawCursor();
  },
  latency(ms) {
    $("metrics").textContent =
      `${Math.round(ms)} MS · ${route.toUpperCase()} · INPUT RTT`;
  },
  error(message) {
    toast(message);
    $("remote-pair-status").textContent = message;
    $("screen-empty").textContent = message;
  },
});
const gesture = new TrackpadGesture((message) => {
  // Drag lock owns the held button until explicitly released.
  if (dragLocked && message.type === "button") return;
  connection.send(message);
});

const storedSpeed = Number(localStorage.getItem("deskpad.speed") || 4);
gesture.speed = Number.isFinite(storedSpeed)
  ? storedSpeed < 2.5
    ? 4
    : Math.min(7, storedSpeed)
  : 4;
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

const cancelPortraitSurface = attachTrackpadSurface(
  pad,
  gesture,
  () => !landscape,
);
const cancelLandscapeSurface = attachTrackpadSurface(
  $("screen"),
  gesture,
  () => landscape && controlMode === "mouse",
);

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
  keyboardWanted = open;
  $("app").classList.toggle("keyboard-open", open);
  $("keyboard-toggle").setAttribute("aria-expanded", String(open));
  $("keyboard-toggle").setAttribute(
    "aria-label",
    open ? "Hide keyboard" : "Open keyboard",
  );
  if (open) typing.focus({ preventScroll: true });
  else typing.blur();
}
$("keyboard-toggle").addEventListener("click", () => keyboard(!keyboardWanted));
typing.addEventListener("blur", () => keyboard(false));
// Do not let desktop controls dismiss the native keyboard.
// Menus explicitly manage focus; the scrollable key row stays focus-neutral on touch.
document
  .querySelectorAll(
    ".controls button,.mouse-row button,.session-brand,.menu-button",
  )
  .forEach((button) => {
    button.addEventListener("pointerdown", (event) => event.preventDefault());
  });
function openSettings() {
  restoreKeyboard = keyboardWanted;
  keyboard(false);
  releaseInputs();
  $("settings").hidden = false;
  $("workspace").inert = true;
  document.querySelector<HTMLElement>(".topbar")!.inert = true;
  $("settings-toggle").setAttribute("aria-expanded", "true");
  $("settings-close").focus({ preventScroll: true });
}
function closeSettings(resume = true) {
  const wasOpen = !$("settings").hidden;
  $("settings").hidden = true;
  $("workspace").inert = false;
  document.querySelector<HTMLElement>(".topbar")!.inert = false;
  $("settings-toggle").setAttribute("aria-expanded", "false");
  if (wasOpen && resume && restoreKeyboard && desiredConnection) keyboard(true);
  restoreKeyboard = false;
}
$("paste-text").addEventListener("click", () => {
  closeSettings(false);
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

// Store trackpad height in pixels, not a screen percentage that shrinks the desktop.
let padHeight = Number(localStorage.getItem("deskpad.padHeight") || 80);
if (!Number.isFinite(padHeight)) padHeight = 80;
function resizePad(value: number) {
  padHeight = Math.max(52, Math.min(200, value));
  document.documentElement.style.setProperty("--pad-height", `${padHeight}px`);
  $("divider").setAttribute("aria-valuenow", String(Math.round(padHeight)));
  localStorage.setItem("deskpad.padHeight", String(padHeight));
}
resizePad(padHeight);
let dividerStart = 0,
  dividerHeight = 0;
$("divider").addEventListener("pointerdown", (event) => {
  event.preventDefault();
  $("divider").setPointerCapture(event.pointerId);
  dividerStart = event.clientY;
  dividerHeight = pad.clientHeight;
});
$("divider").addEventListener("pointermove", (event) => {
  if ($("divider").hasPointerCapture(event.pointerId))
    resizePad(dividerHeight + dividerStart - event.clientY);
});
$("divider").addEventListener("keydown", (event) => {
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    resizePad(padHeight + (event.key === "ArrowUp" ? 12 : -12));
  }
});
const mousePreference = $<HTMLInputElement>("show-mouse-buttons");
mousePreference.checked =
  localStorage.getItem("deskpad.mouseButtons") === "true";
$("mouse-buttons").hidden = !mousePreference.checked;
mousePreference.addEventListener("change", () => {
  releaseInputs();
  $("mouse-buttons").hidden = !mousePreference.checked;
  localStorage.setItem("deskpad.mouseButtons", String(mousePreference.checked));
});
const wheelPreference = $<HTMLInputElement>("show-scroll-wheel");
const wheel = $("scroll-wheel");
wheelPreference.checked =
  localStorage.getItem("deskpad.scrollWheel") === "true";
wheel.hidden = !wheelPreference.checked;
wheelPreference.addEventListener("change", () => {
  wheelPointer = undefined;
  wheel.classList.remove("engaged");
  wheel.hidden = !wheelPreference.checked;
  localStorage.setItem("deskpad.scrollWheel", String(wheelPreference.checked));
});
let wheelPointer: number | undefined,
  wheelY = 0;
wheel.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  if (wheelPointer !== undefined) return;
  wheelPointer = event.pointerId;
  wheelY = event.clientY;
  wheel.setPointerCapture(event.pointerId);
  wheel.classList.add("engaged");
});
wheel.addEventListener("pointermove", (event) => {
  if (event.pointerId !== wheelPointer) return;
  const delta = (-(event.clientY - wheelY) * (gesture.natural ? 1 : -1)) / 24;
  wheelY = event.clientY;
  connection.send({
    type: "scroll",
    dx: 0,
    dy: Math.max(-100, Math.min(100, delta)),
  });
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
  wheel.addEventListener(name, (event) => {
    if ((event as PointerEvent).pointerId === wheelPointer) {
      wheelPointer = undefined;
      wheel.classList.remove("engaged");
    }
  });
wheel.addEventListener("keydown", (event) => {
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    connection.send({
      type: "scroll",
      dx: 0,
      dy: event.key === "ArrowDown" ? 1 : -1,
    });
  }
});
$("reset-view").addEventListener("click", () => {
  viewer.reset();
});

function setControlMode(mode: "mouse" | "view") {
  releaseInputs();
  controlMode = mode;
  viewer.setEnabled(!landscape || mode === "view");
  $("app").classList.toggle("view-mode", landscape && mode === "view");
  $("mouse-mode").setAttribute("aria-pressed", String(mode === "mouse"));
  $("view-mode").setAttribute("aria-pressed", String(mode === "view"));
  $("screen").setAttribute(
    "aria-label",
    landscape && mode === "mouse"
      ? "Desktop trackpad. Slide to move the mouse; tap to click; two fingers to scroll."
      : "Laptop screen. Pinch to zoom; drag to pan.",
  );
}
$("mouse-mode").addEventListener("click", () => setControlMode("mouse"));
$("view-mode").addEventListener("click", () => setControlMode("view"));
function updateDock() {
  $("app").classList.toggle("dock-collapsed", dockCollapsed);
  $("bar-toggle").textContent = dockCollapsed ? "▴" : "▾";
  $("bar-toggle").setAttribute("aria-expanded", String(!dockCollapsed));
  $("bar-toggle").setAttribute(
    "aria-label",
    dockCollapsed ? "Expand hotkeys" : "Collapse hotkeys",
  );
}
$("bar-toggle").addEventListener("click", () => {
  releaseInputs();
  dockCollapsed = !dockCollapsed;
  localStorage.setItem("deskpad.dockCollapsed", String(dockCollapsed));
  updateDock();
});
updateDock();
function updateOrientation() {
  const type = window.screen.orientation?.type;
  const legacyAngle = (window as Window & { orientation?: number }).orientation;
  const next = type
    ? type.startsWith("landscape")
    : typeof legacyAngle === "number"
      ? Math.abs(legacyAngle) === 90
      : window.screen.width > window.screen.height;
  if (next === landscape) return;
  releaseInputs();
  if (next) {
    portraitKeyboard = keyboardWanted;
    keyboard(false);
  }
  landscape = next;
  $("app").classList.toggle("landscape", landscape);
  viewer.setOrientation(landscape ? "landscape" : "portrait");
  $("reset-view").textContent = landscape ? "Fit desktop" : "Fit width";
  setControlMode("mouse");
  if (!landscape && portraitKeyboard && desiredConnection) keyboard(true);
}
window.screen.orientation?.addEventListener("change", updateOrientation);
window.addEventListener("orientationchange", updateOrientation);
window.addEventListener("resize", updateOrientation);
updateOrientation();

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
  cancelPortraitSurface();
  cancelLandscapeSurface();
  wheelPointer = undefined;
  wheel.classList.remove("engaged");
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
$("settings-toggle").addEventListener("click", openSettings);
$("brand-status").addEventListener("click", openSettings);
$("rail-brand").addEventListener("click", openSettings);
$("landscape-settings").addEventListener("click", openSettings);
$("settings-close").addEventListener("click", () => closeSettings());
$("settings-done").addEventListener("click", () => closeSettings());
const settingTabs = Array.from(
  document.querySelectorAll<HTMLButtonElement>("[data-panel]"),
);
function selectSettingsTab(tab: HTMLButtonElement) {
  for (const item of settingTabs) {
    const selected = item === tab;
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
    $(`panel-${item.dataset.panel}`).hidden = !selected;
  }
  $("settings").querySelector(".settings-body")!.scrollTop = 0;
}
for (const [index, tab] of settingTabs.entries()) {
  tab.addEventListener("click", () => selectSettingsTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? settingTabs.length - 1
          : (index +
              (event.key === "ArrowRight" ? 1 : -1) +
              settingTabs.length) %
            settingTabs.length;
    selectSettingsTab(settingTabs[next]);
    settingTabs[next].focus();
  });
}
$("settings").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    closeSettings();
  }
});
$("disconnect").addEventListener("click", () => {
  desiredConnection = false;
  connection.stop();
  keyboard(false);
  closeSettings(false);
  showEnded("ended");
});
$("reconnect").addEventListener("click", () => {
  desiredConnection = true;
  connection.start();
  closeSettings();
});

function enterWorkspace(demo: boolean) {
  sessionStorage.removeItem("deskpad.sessionEnded");
  $("pairing").hidden = true;
  $("workspace").hidden = false;
  $("app").classList.add("in-session");
  $("demo-label").hidden = !demo;
  desiredConnection = true;
  connection.start();
}
$("pair-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("pair-error").textContent = "";
  const button =
    document.querySelector<HTMLButtonElement>("#pair-form button")!;
  const code = $<HTMLInputElement>("pair-code").value;
  button.disabled = true;
  // Safari needs a user gesture to open the keyboard. Transfer focus now,
  // while the submit gesture is active, rather than after the network response.
  if (!landscape) keyboard(true);
  try {
    const response = await fetch("/api/pair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const body = await response.json();
    if (!response.ok)
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : "Enter the six-digit host code.",
      );
    const status = await (await fetch("/api/status")).json();
    enterWorkspace(status.demo);
  } catch (error) {
    keyboard(false);
    $("pair-error").textContent =
      error instanceof Error ? error.message : "Could not connect.";
  } finally {
    button.disabled = false;
  }
});
for (const [id, kind] of [
  ["phone-camera", "camera"],
  ["phone-microphone", "microphone"],
] as const) {
  const control = $<HTMLInputElement>(id);
  control.addEventListener("change", async () => {
    control.disabled = true;
    try {
      await connection.media(kind, control.checked, cameraFacing);
    } catch (error) {
      control.checked = false;
      toast(error instanceof Error ? error.message : "Media unavailable");
    } finally {
      control.disabled = false;
    }
  });
}
$<HTMLInputElement>("phone-speaker").addEventListener(
  "change",
  async (event) => {
    const control = event.target as HTMLInputElement;
    connection.listen(control.checked);
    if (!control.checked) {
      laptopAudio.pause();
      return;
    }
    try {
      await laptopAudio.play();
    } catch {
      control.checked = false;
      connection.listen(false);
      toast("Connect first and allow laptop audio in desktop Settings.");
    }
  },
);
$("flip-camera").addEventListener("click", async () => {
  if (!$<HTMLInputElement>("phone-camera").checked) {
    toast("Enable your phone camera first.");
    return;
  }
  cameraFacing = cameraFacing === "user" ? "environment" : "user";
  try {
    await connection.media("camera", true, cameraFacing);
  } catch (error) {
    $<HTMLInputElement>("phone-camera").checked = false;
    toast(String(error));
  }
});
$("remote-connect").addEventListener("click", () => {
  const name = $<HTMLInputElement>("phone-name").value.trim() || "My phone";
  localStorage.setItem("deskpad.phoneName", name.slice(0, 64));
  $("remote-pair-status").textContent = "Requesting approval from your laptop…";
  desiredConnection = true;
  connection.start();
});
if (connection.remote) {
  $("scan-qr").hidden = false;
  $("scan-qr").textContent = "Scan a new QR";
  $("pairing").hidden = false;
  $("pair-form").hidden = true;
  $("local-pair-description").hidden = true;
  $("remote-pair").hidden = false;
  $("pair-title").textContent = connection.remote.name || "Your laptop";
  $("pair-note").textContent = "Approve on your laptop · No account needed";
  if (connection.remote.approved) {
    $("remote-connect").textContent = "Reconnect to laptop";
    if (sessionStorage.getItem("deskpad.sessionEnded")) showEnded("ended");
    else enterWorkspace(false);
  }
} else
  void fetch("/api/status")
    .then((r) => r.json())
    .then((status) => {
      if (status.remoteService) {
        $("scan-qr").hidden = false;
        $("pair-form").hidden = true;
        $("local-pair-description").textContent =
          "Open Deskpad on your laptop and scan its QR code to pair this phone.";
        $("pair-note").textContent = "Your laptop. Wherever you are.";
      }
      if (status.paired) {
        if (sessionStorage.getItem("deskpad.sessionEnded")) showEnded("ended");
        else enterWorkspace(status.demo);
      } else $("pairing").hidden = false;
    })
    .catch(() => {
      $("pairing").hidden = false;
      $("pair-error").textContent =
        "Cannot reach the host. Keep Deskpad running on your laptop, then reload.";
    });

$("scan-qr").addEventListener("click", () => {
  void import("./scanner")
    .then(({ scanQR }) => scanQR())
    .catch(() => {
      $("pair-error").textContent =
        "Could not load scanner. Try your phone's Camera app.";
    });
});

$("session-resume").addEventListener("click", () => enterWorkspace(false));

$("monitor-switch").addEventListener("pointerdown", () => {
  monitorKeyboardRestore = keyboardWanted;
  releaseInputs();
});
$("monitor-switch").addEventListener("change", () => {
  connection.send({
    type: "display",
    monitor: Number($<HTMLSelectElement>("monitor-switch").value),
  });
  if (monitorKeyboardRestore) keyboard(true);
  monitorKeyboardRestore = false;
});
$("follow-cursor").addEventListener("change", () => {
  const follow = $<HTMLInputElement>("follow-cursor").checked;
  localStorage.setItem("deskpad.followCursor", String(follow));
  connection.send({ type: "display", follow_cursor: follow });
});

$("actions-toggle").addEventListener("click", () => {
  const show = $("quick-actions").hidden;
  $("quick-actions").hidden = !show;
  $("desktop-keys").hidden = show;
  $("actions-toggle").setAttribute("aria-expanded", String(show));
  $("actions-toggle").setAttribute(
    "aria-label",
    show ? "Show desktop keys" : "Show quick actions",
  );
});
