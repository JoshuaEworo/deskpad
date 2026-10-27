import { TrackpadGesture } from "./gestures";

/** Bind the same relative-input gestures to the portrait pad or landscape screen. */
export function attachTrackpadSurface(
  surface: HTMLElement,
  gesture: TrackpadGesture,
  enabled: () => boolean,
) {
  const contacts = new Set<number>();
  let holdTimer: ReturnType<typeof setTimeout>;
  const cancel = () => {
    clearTimeout(holdTimer);
    contacts.clear();
    gesture.cancel();
    surface.classList.remove("engaged");
  };
  surface.addEventListener("pointerdown", (event) => {
    if (!enabled() || (event.target as Element).closest("button")) return;
    event.preventDefault();
    contacts.add(event.pointerId);
    surface.setPointerCapture(event.pointerId);
    surface.classList.add("engaged");
    gesture.down(
      event.pointerId,
      event.clientX,
      event.clientY,
      performance.now(),
    );
    clearTimeout(holdTimer);
    holdTimer = setTimeout(() => gesture.hold(performance.now()), 365);
  });
  surface.addEventListener("pointermove", (event) => {
    if (enabled() && contacts.has(event.pointerId)) {
      gesture.move(event.pointerId, event.clientX, event.clientY);
    }
  });
  surface.addEventListener("pointerup", (event) => {
    if (!contacts.delete(event.pointerId)) return;
    gesture.up(event.pointerId, performance.now());
    surface.classList.remove("engaged");
    clearTimeout(holdTimer);
  });
  surface.addEventListener("pointercancel", cancel);
  surface.addEventListener("lostpointercapture", (event) => {
    if (contacts.has(event.pointerId)) cancel();
  });
  surface.addEventListener("contextmenu", (event) => event.preventDefault());
  return cancel;
}
