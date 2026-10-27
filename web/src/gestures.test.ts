import { describe, expect, it } from "vitest";
import { TrackpadGesture } from "./gestures";
import type { Input } from "./protocol";

function setup() {
  const events: Input[] = [];
  return { events, pad: new TrackpadGesture((m) => events.push(m)) };
}

describe("trackpad gesture ownership", () => {
  it("clicks once for a tap and never after motion", () => {
    const { pad, events } = setup();
    pad.down(1, 0, 0, 0);
    pad.up(1, 80);
    expect(events).toEqual([
      { type: "button", button: "left", action: "click" },
    ]);
    events.length = 0;
    pad.down(2, 0, 0, 1000);
    pad.move(2, 20, 30);
    pad.up(2, 1100);
    expect(events).toEqual([{ type: "move", dx: 30, dy: 45 }]);
  });
  it("releases a long-press drag on cancellation", () => {
    const { pad, events } = setup();
    pad.down(1, 0, 0, 0);
    pad.hold(360);
    pad.move(1, 20, 20);
    pad.cancel();
    expect(events[0]).toEqual({
      type: "button",
      button: "left",
      action: "down",
    });
    expect(events.at(-1)).toEqual({
      type: "button",
      button: "left",
      action: "up",
    });
  });
  it("makes a two-finger right click without a ghost left click", () => {
    const { pad, events } = setup();
    pad.down(1, 10, 10, 0);
    pad.down(2, 30, 10, 15);
    pad.up(1, 60);
    pad.up(2, 90);
    expect(events).toEqual([
      { type: "button", button: "right", action: "click" },
    ]);
  });
  it("does not move the cursor when one finger remains after scrolling", () => {
    const { pad, events } = setup();
    pad.down(1, 0, 0, 0);
    pad.down(2, 20, 0, 10);
    pad.move(1, 0, 30);
    pad.up(2, 100);
    pad.move(1, 0, 80);
    pad.up(1, 150);
    expect(events.every((e) => e.type === "scroll")).toBe(true);
  });
  it("supports double-tap and drag and releases exactly once", () => {
    const { pad, events } = setup();
    pad.down(1, 0, 0, 0);
    pad.up(1, 50);
    pad.down(2, 0, 0, 140);
    pad.move(2, 50, 0);
    pad.up(2, 300);
    expect(events.filter((e) => e.type === "button")).toEqual([
      { type: "button", button: "left", action: "click" },
      { type: "button", button: "left", action: "down" },
      { type: "button", button: "left", action: "up" },
    ]);
  });
});
