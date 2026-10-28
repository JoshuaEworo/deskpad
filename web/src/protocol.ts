export type Input =
  | { type: "media"; kind: "camera" | "microphone"; enabled: boolean }
  | { type: "move"; dx: number; dy: number }
  | { type: "scroll"; dx: number; dy: number }
  | {
      type: "button";
      button: "left" | "right";
      action: "down" | "up" | "click";
    }
  | { type: "key"; key: string; action: "down" | "up" | "press" }
  | { type: "text"; text: string }
  | { type: "shortcut"; keys: string[] }
  | { type: "release" }
  | { type: "ping"; timestamp: number };

export type Frame = {
  type: "frame";
  sequence: number;
  width: number;
  height: number;
  bounds: { left: number; top: number; width: number; height: number };
  cursor: [number, number];
};
