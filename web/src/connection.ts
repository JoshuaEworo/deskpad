import type { Frame, Input } from "./protocol";

type State =
  "connecting" | "connected" | "disconnected" | "busy" | "unpaired" | "paused";
type Hooks = {
  state: (state: State) => void;
  frame: (blob: Blob, meta: Frame) => Promise<void>;
  cursor: (position: [number, number]) => void;
  latency: (ms: number) => void;
  error: (message: string) => void;
};

export class Connection {
  private control?: WebSocket;
  private video?: WebSocket;
  private heartbeat?: ReturnType<typeof setInterval>;
  private retry?: ReturnType<typeof setTimeout>;
  private alive = false;
  private attempts = 0;
  private generation = 0;
  private moveX = 0;
  private moveY = 0;
  private animation = 0;

  constructor(private hooks: Hooks) {}

  start() {
    this.stop();
    this.alive = true;
    this.attempts = 0;
    this.connect();
  }

  private connect() {
    const generation = ++this.generation;
    this.hooks.state("connecting");
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const control = new WebSocket(`${scheme}//${location.host}/ws/control`);
    this.control = control;
    let initialized = false;
    control.onmessage = (event) => {
      if (generation !== this.generation) return;
      const data = JSON.parse(event.data);
      if (data.type === "hello") {
        if (data.protocol !== 1) {
          this.hooks.error("Host and phone versions differ. Reload Deskpad.");
          this.stop();
          return;
        }
        initialized = true;
        this.attempts = 0;
        this.hooks.state("connected");
        this.hooks.cursor(data.cursor);
        this.heartbeat = setInterval(
          () => this.send({ type: "ping", timestamp: performance.now() }),
          2000,
        );
        this.openVideo(scheme, data.connection, generation);
      } else if (data.type === "pong")
        this.hooks.latency(performance.now() - data.timestamp);
      else if (data.type === "cursor") this.hooks.cursor(data.position);
      else if (data.type === "error") this.hooks.error(data.message);
    };
    control.onclose = (event) => {
      if (generation !== this.generation) return;
      clearInterval(this.heartbeat);
      this.video?.close();
      this.moveX = this.moveY = 0;
      if (!this.alive) return;
      if (event.code === 4409) {
        this.hooks.state("busy");
        return;
      }
      if (
        event.code === 4403 ||
        (!initialized && event.code === 1006 && this.attempts >= 2)
      ) {
        // Browser handshakes can hide the server's rejection code; ask HTTP status before retrying.
        void fetch("/api/status")
          .then((r) => r.json())
          .then((s) => {
            if (generation !== this.generation) return;
            if (!s.paired) this.hooks.state("unpaired");
            else if (s.busy) this.hooks.state("busy");
            else this.scheduleRetry();
          })
          .catch(() => {
            if (generation === this.generation) this.scheduleRetry();
          });
      } else this.scheduleRetry();
    };
  }

  private scheduleRetry() {
    this.hooks.state("disconnected");
    if (this.alive)
      this.retry = setTimeout(
        () => this.connect(),
        Math.min(5000, 750 * 2 ** this.attempts++),
      );
  }

  private openVideo(scheme: string, connection: string, generation: number) {
    const video = new WebSocket(
      `${scheme}//${location.host}/ws/video?connection=${encodeURIComponent(connection)}`,
    );
    this.video = video;
    video.binaryType = "blob";
    let meta: Frame | undefined;
    video.onmessage = async (event) => {
      if (generation !== this.generation) return;
      if (typeof event.data === "string") {
        const data = JSON.parse(event.data);
        if (data.type === "frame") meta = data;
        else if (data.type === "error") this.hooks.error(data.message);
      } else if (meta) {
        try {
          await this.hooks.frame(event.data, meta);
          if (
            video.readyState === WebSocket.OPEN &&
            generation === this.generation
          )
            video.send("ack");
        } catch {
          this.hooks.error("Could not decode the desktop image.");
          video.close();
        }
      }
    };
    video.onclose = () => {
      if (
        generation === this.generation &&
        this.control?.readyState === WebSocket.OPEN
      ) {
        this.hooks.error("Screen stream stopped. Reconnecting…");
        this.control.close();
      }
    };
  }

  send(message: Input) {
    if (message.type === "move") {
      this.moveX += message.dx;
      this.moveY += message.dy;
      if (!this.animation)
        this.animation = requestAnimationFrame(() => {
          this.animation = 0;
          this.flushMovement();
        });
      return;
    }
    // Preserve pointer movement order relative to button transitions.
    this.flushMovement();
    this.write(message);
  }

  private flushMovement() {
    if (this.moveX || this.moveY) {
      this.write({
        type: "move",
        dx: Math.max(-2000, Math.min(2000, this.moveX)),
        dy: Math.max(-2000, Math.min(2000, this.moveY)),
      });
      this.moveX = this.moveY = 0;
    }
  }

  private write(message: Input) {
    if (this.control?.readyState !== WebSocket.OPEN) return;
    if (this.control.bufferedAmount > 65536) {
      this.hooks.error(
        "Connection too slow. Reconnecting without replaying old input.",
      );
      this.control.close();
      return;
    }
    this.control.send(JSON.stringify(message));
  }

  release() {
    this.send({ type: "release" });
  }

  stop() {
    this.release();
    this.alive = false;
    this.generation++;
    clearTimeout(this.retry);
    clearInterval(this.heartbeat);
    cancelAnimationFrame(this.animation);
    this.animation = 0;
    this.control?.close();
    this.video?.close();
    this.moveX = this.moveY = 0;
    this.hooks.state("paused");
  }
}
