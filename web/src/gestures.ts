import type { Input } from "./protocol";

type Point = { x: number; y: number; startX: number; startY: number };

/** Pure gesture state machine. All contacts must end before a new gesture starts. */
export class TrackpadGesture {
  private points = new Map<number, Point>();
  private started = 0;
  private travel = 0;
  private maxContacts = 0;
  private dragging = false;
  private lastTap = -Infinity;
  private lastTapPoint = { x: 0, y: 0 };
  speed = 4;
  natural = true;

  constructor(private emit: (message: Input) => void) {}

  down(id: number, x: number, y: number, now: number) {
    if (!this.points.size) {
      this.started = now;
      this.travel = 0;
      this.maxContacts = 0;
      if (
        now - this.lastTap < 260 &&
        Math.hypot(x - this.lastTapPoint.x, y - this.lastTapPoint.y) < 28
      ) {
        this.dragging = true;
        this.emit({ type: "button", button: "left", action: "down" });
      }
    } else if (this.dragging) {
      this.emit({ type: "button", button: "left", action: "up" });
      this.dragging = false;
    }
    this.points.set(id, { x, y, startX: x, startY: y });
    this.maxContacts = Math.max(this.maxContacts, this.points.size);
  }

  move(id: number, x: number, y: number) {
    const point = this.points.get(id);
    if (!point) return;
    const dx = x - point.x,
      dy = y - point.y;
    point.x = x;
    point.y = y;
    this.travel = Math.max(
      this.travel,
      Math.hypot(x - point.startX, y - point.startY),
    );
    if (this.maxContacts === 1) {
      this.emit({ type: "move", dx: dx * this.speed, dy: dy * this.speed });
    } else if (this.maxContacts === 2 && this.points.size === 2) {
      const direction = this.natural ? 1 : -1;
      // Each contact contributes half of the centroid delta.
      this.emit({
        type: "scroll",
        dx: (-dx * direction) / 48,
        dy: (-dy * direction) / 48,
      });
    }
  }

  hold(now: number) {
    if (
      this.points.size === 1 &&
      this.maxContacts === 1 &&
      this.travel < 7 &&
      now - this.started >= 350 &&
      !this.dragging
    ) {
      this.dragging = true;
      this.emit({ type: "button", button: "left", action: "down" });
    }
  }

  up(id: number, now: number) {
    const point = this.points.get(id);
    this.points.delete(id);
    if (this.points.size || !point) return;
    if (this.dragging) {
      this.emit({ type: "button", button: "left", action: "up" });
      this.dragging = false;
      this.lastTap = -Infinity;
    } else if (this.travel < 7 && now - this.started < 350) {
      if (this.maxContacts === 1) {
        this.emit({ type: "button", button: "left", action: "click" });
        this.lastTap = now;
        this.lastTapPoint = { x: point.x, y: point.y };
      } else if (this.maxContacts === 2) {
        this.emit({ type: "button", button: "right", action: "click" });
        this.lastTap = -Infinity;
      }
    }
    this.maxContacts = 0;
  }

  cancel() {
    if (this.dragging)
      this.emit({ type: "button", button: "left", action: "up" });
    this.points.clear();
    this.dragging = false;
    this.maxContacts = 0;
    this.lastTap = -Infinity;
  }
}
