import type { Input } from "./protocol";

export function attachGamepad(
  controls: HTMLElement,
  send: (input: Input) => void,
  enabled: () => boolean,
  menuCursor: () => boolean,
) {
  const stick = controls.querySelector<HTMLElement>("#game-stick")!;
  const look = controls.querySelector<HTMLElement>("#game-look")!;
  const held = new Map<HTMLButtonElement, number>();
  let stickPointer: number | undefined;
  let lookPointer: number | undefined;
  let startX = 0, startY = 0, lastX = 0, lastY = 0, travel = 0;
  let dx = 0, dy = 0, animation = 0;
  const directions = new Set<string>();

  function moveStick(x: number, y: number) {
    const radius = Math.hypot(x, y);
    const scale = radius > 1 ? 1 / radius : 1;
    stick.style.setProperty("--stick-x", `${x * scale * 25}px`);
    stick.style.setProperty("--stick-y", `${y * scale * 25}px`);
    for (const [key, axis] of [["w", -y], ["s", y], ["a", -x], ["d", x]] as const) {
      const down = directions.has(key);
      // Hysteresis keeps a thumb near the threshold from flickering the key.
      const next = axis > (down ? 0.20 : 0.32);
      if (next === down) continue;
      if (next) directions.add(key);
      else directions.delete(key);
      send({ type: "key", key, action: next ? "down" : "up" });
    }
  }

  function positionStick(event: PointerEvent) {
    const bounds = stick.getBoundingClientRect();
    moveStick(
      (event.clientX - bounds.left - bounds.width / 2) / (bounds.width / 2),
      (event.clientY - bounds.top - bounds.height / 2) / (bounds.height / 2),
    );
  }

  stick.addEventListener("pointerdown", (event) => {
    if (!enabled() || stickPointer !== undefined || event.button !== 0) return;
    event.preventDefault();
    stickPointer = event.pointerId;
    stick.setPointerCapture(event.pointerId);
    positionStick(event);
  });
  stick.addEventListener("pointermove", (event) => {
    if (event.pointerId === stickPointer) positionStick(event);
  });

  function flushLook() {
    cancelAnimationFrame(animation);
    animation = 0;
    if (!dx && !dy) return;
    send({
      type: "look",
      dx: Math.max(-2000, Math.min(2000, dx)),
      dy: Math.max(-2000, Math.min(2000, dy)),
    });
    dx = dy = 0;
  }

  look.addEventListener("pointerdown", (event) => {
    if (!enabled() || lookPointer !== undefined || event.button !== 0) return;
    event.preventDefault();
    lookPointer = event.pointerId;
    look.setPointerCapture(event.pointerId);
    startX = lastX = event.clientX;
    startY = lastY = event.clientY;
    travel = 0;
  });
  look.addEventListener("pointermove", (event) => {
    if (event.pointerId !== lookPointer) return;
    travel = Math.max(travel, Math.hypot(event.clientX - startX, event.clientY - startY));
    if (menuCursor() && travel < 6) return;
    dx += (event.clientX - lastX) * 1.6;
    dy += (event.clientY - lastY) * 1.6;
    lastX = event.clientX;
    lastY = event.clientY;
    if (!animation) animation = requestAnimationFrame(flushLook);
  });

  const endEvents = ["pointerup", "pointercancel", "lostpointercapture"] as const;
  for (const name of endEvents) {
    stick.addEventListener(name, (event) => {
      if (event.pointerId !== stickPointer) return;
      stickPointer = undefined;
      moveStick(0, 0);
    });
    look.addEventListener(name, (event) => {
      if (event.pointerId !== lookPointer) return;
      lookPointer = undefined;
      if (name !== "pointerup") {
        cancelAnimationFrame(animation);
        animation = dx = dy = 0;
        return;
      }
      flushLook();
      if (menuCursor() && travel < 6)
        send({ type: "button", button: "left", action: "click" });
    });
  }

  for (const button of controls.querySelectorAll<HTMLButtonElement>(
    "[data-game-key], [data-game-button]",
  )) {
    const key = button.dataset.gameKey;
    const mouse = button.dataset.gameButton === "left" ? "left" : "right";
    function action(value: "up" | "down") {
      flushLook();
      send(key ? { type: "key", key, action: value } : { type: "button", button: mouse, action: value });
    }
    button.addEventListener("pointerdown", (event) => {
      if (!enabled() || held.has(button) || event.button !== 0) return;
      event.preventDefault();
      held.set(button, event.pointerId);
      button.setPointerCapture(event.pointerId);
      button.classList.add("held");
      action("down");
    });
    for (const name of endEvents)
      button.addEventListener(name, (event) => {
        if (held.get(button) !== event.pointerId) return;
        held.delete(button);
        button.classList.remove("held");
        action("up");
      });
    button.addEventListener("click", (event) => {
      if (!enabled() || event.detail !== 0) return;
      action("down");
      action("up");
    });
  }

  const toggles = controls.querySelectorAll<HTMLButtonElement>("[data-game-toggle]");
  for (const button of toggles)
    button.addEventListener("click", () => {
      if (!enabled()) return;
      const down = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", String(down));
      send({ type: "key", key: button.dataset.gameToggle!, action: down ? "down" : "up" });
    });
  for (const button of controls.querySelectorAll<HTMLButtonElement>("[data-game-press], [data-game-slot]"))
    button.addEventListener("click", () => {
      if (!enabled()) return;
      flushLook();
      const key = button.dataset.gamePress;
      send(key
        ? { type: "key", key, action: "press" }
        : { type: "scroll", dx: 0, dy: Number(button.dataset.gameSlot) });
    });

  // The caller sends one release-all message for the whole session.
  return () => {
    cancelAnimationFrame(animation);
    animation = dx = dy = 0;
    stickPointer = lookPointer = undefined;
    directions.clear();
    moveStick(0, 0);
    for (const button of held.keys()) button.classList.remove("held");
    held.clear();
    for (const button of toggles) button.setAttribute("aria-pressed", "false");
  };
}
