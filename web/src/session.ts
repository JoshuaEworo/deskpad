import { Connection as LegacyConnection, type Hooks } from "./connection";
import { RtcConnection } from "./rtc-connection";
import { remoteConfig, type RemoteConfig } from "./remote-identity";
import type { Input } from "./protocol";

export class Connection {
  private transport?: LegacyConnection | RtcConnection;
  private generation = 0;
  remote?: RemoteConfig;
  constructor(private hooks: Hooks) {
    try {
      this.remote = remoteConfig();
    } catch (error) {
      queueMicrotask(() => hooks.error(String(error)));
    }
  }
  start() {
    this.stop();
    const generation = ++this.generation;
    if (this.remote) {
      this.transport = new RtcConnection(this.hooks, this.remote);
      this.transport.start();
      return;
    }
    void fetch("/api/status")
      .then((r) => r.json())
      .then((status) => {
        if (generation !== this.generation) return;
        // JPEG remains available for source installs without the media extra.
        // RTC can be disabled explicitly when diagnosing compatibility.
        this.transport =
          status.rtc && localStorage.getItem("deskpad.legacyVideo") !== "true"
            ? new RtcConnection(this.hooks)
            : new LegacyConnection(this.hooks);
        this.transport.start();
      })
      .catch(() => this.hooks.error("Cannot reach the laptop"));
  }
  send(message: Input) {
    this.transport?.send(message);
  }
  release() {
    this.transport?.release();
  }
  stop() {
    this.generation++;
    this.transport?.stop();
    this.transport = undefined;
  }
  async media(
    kind: "camera" | "microphone",
    enabled: boolean,
    facing: "user" | "environment" = "user",
  ) {
    if (!(this.transport instanceof RtcConnection))
      throw new Error(
        "Phone media requires WebRTC. Install the desktop/media build.",
      );
    await this.transport.media(kind, enabled, facing);
  }
}
