import type { Hooks } from "./connection";
import type { Input } from "./protocol";
import {
  nonce,
  phoneKeys,
  sign,
  verify,
  saveRemote,
  pairingCode,
  type RemoteConfig,
} from "./remote-identity";

export class RtcConnection {
  private pc?: RTCPeerConnection;
  private channel?: RTCDataChannel;
  private socket?: WebSocket;
  private keys?: CryptoKeyPair;
  private heartbeat?: ReturnType<typeof setInterval>;
  private retry?: ReturnType<typeof setTimeout>;
  private timeout?: ReturnType<typeof setTimeout>;
  private alive = false;
  private generation = 0;
  private pending = new Map<string, string>();
  private camera?: RTCRtpSender;
  private microphone?: RTCRtpSender;
  private tracks = new Map<string, MediaStreamTrack>();
  private mediaGeneration = { camera: 0, microphone: 0 };
  private moves = [0, 0];
  private animation = 0;
  private processing = Promise.resolve();
  constructor(
    private hooks: Hooks,
    private remote?: RemoteConfig,
  ) {}

  start() {
    this.stop();
    this.alive = true;
    const generation = ++this.generation;
    this.hooks.state("connecting");
    this.timeout = setTimeout(() => {
      if (this.alive && generation === this.generation) {
        this.hooks.error(
          "Connection timed out. Keep your laptop online and approve pairing there.",
        );
        this.failed();
      }
    }, 45000);
    void this.connect(generation).catch((error) =>
      this.error(error, generation),
    );
  }
  private async connect(generation: number) {
    if (!this.remote) {
      await this.makePeer([], generation);
      const offer = await this.offer();
      const response = await fetch("/api/rtc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sdp: offer.sdp }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Could not start stream",
        );
      if (generation !== this.generation) return;
      await this.pc!.setRemoteDescription({ type: "answer", sdp: result.sdp });
      return;
    }
    this.keys = await phoneKeys(this.remote.room);
    if (generation !== this.generation) return;
    const socket = new WebSocket(
      `${location.origin.replace("https:", "wss:")}/api/rooms/${this.remote.room}/socket`,
      ["deskpad", `phone.${this.remote.gate}`],
    );
    this.socket = socket;
    socket.onopen = () => {
      if (generation !== this.generation) return;
      void this.request(
        this.remote!.approved ? "connect" : "pair",
        this.remote!.approved
          ? {}
          : {
              invite: this.remote!.invite,
              name: localStorage.getItem("deskpad.phoneName") || "My phone",
            },
      ).catch((error) => this.error(error, generation));
    };
    socket.onmessage = (event) => {
      this.processing = this.processing
        .then(async () => {
          if (generation !== this.generation) return;
          const result = await verify(
            JSON.parse(event.data),
            this.remote!.host,
          );
          if (generation !== this.generation) return;
          const expected = this.pending.get(result.nonce);
          if (!expected)
            throw new Error("Unexpected or replayed laptop response");
          if (result.kind === "pending" && expected === "pair") {
            const publicKey = await crypto.subtle.exportKey(
              "jwk",
              this.keys!.publicKey,
            );
            const code = await pairingCode(this.remote!.host, publicKey);
            if (code !== result.code)
              throw new Error("Pairing verification failed");
            this.hooks.pairing?.(code);
            clearTimeout(this.timeout);
            this.timeout = setTimeout(() => this.failed(), 120000);
            return;
          }
          this.pending.delete(result.nonce);
          if (result.kind === "error") throw new Error(result.message);
          if (result.kind === "approved" && expected === "pair") {
            this.remote!.approved = true;
            delete this.remote!.invite;
            saveRemote(this.remote!);
            await this.request("connect", {});
          } else if (result.kind === "config" && expected === "connect") {
            await this.makePeer(result.ice, generation);
            const offer = await this.offer();
            await this.request("offer", {
              challenge: result.challenge,
              sdp: offer.sdp,
            });
          } else if (result.kind === "answer" && expected === "offer") {
            await this.pc!.setRemoteDescription({
              type: "answer",
              sdp: result.sdp,
            });
          } else throw new Error("Unexpected laptop response");
        })
        .catch((error) => this.error(error, generation));
    };
    socket.onclose = () => {
      if (
        generation === this.generation &&
        this.alive &&
        this.pc?.connectionState !== "connected"
      )
        this.failed();
    };
  }
  private async request(kind: string, body: Record<string, unknown>) {
    const id = nonce();
    this.pending.set(id, kind);
    const envelope = await sign(this.keys!, {
      kind,
      ...body,
      nonce: id,
      time: Date.now() / 1000,
    });
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify({ message: envelope }));
  }
  private async makePeer(ice: RTCIceServer[], generation: number) {
    if (generation !== this.generation) return;
    const pc = new RTCPeerConnection({
      iceServers: ice,
      bundlePolicy: "max-bundle",
    });
    this.pc = pc;
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });
    this.camera = pc.addTransceiver("video", { direction: "sendonly" }).sender;
    this.microphone = pc.addTransceiver("audio", {
      direction: "sendonly",
    }).sender;
    const channel = pc.createDataChannel("control", { ordered: true });
    this.channel = channel;
    channel.onopen = () => {
      if (generation !== this.generation) return;
      clearTimeout(this.timeout);
      this.hooks.state("connected");
      this.heartbeat = setInterval(() => {
        this.send({ type: "ping", timestamp: performance.now() });
        void this.route();
      }, 2000);
      this.send({ type: "ping", timestamp: performance.now() });
    };
    channel.onmessage = (event) => {
      if (generation !== this.generation) return;
      const result = JSON.parse(event.data);
      if (result.type === "hello") this.hooks.mediaAllowed?.(result.media);
      else if (result.type === "frame") this.hooks.metadata?.(result);
      else if (result.type === "cursor") this.hooks.cursor(result.position);
      else if (result.type === "pong")
        this.hooks.latency(performance.now() - result.timestamp);
      else if (result.type === "media-status")
        this.hooks.mediaError?.(result.kind, result.error);
      else if (result.type === "error") this.hooks.error(result.message);
    };
    channel.onclose = () => {
      if (generation === this.generation && this.alive) this.failed();
    };
    pc.ontrack = (event) => {
      if (generation !== this.generation) return;
      this.hooks.stream?.(new MediaStream([event.track]), event.track.kind);
    };
    pc.onconnectionstatechange = () => {
      if (
        generation === this.generation &&
        ["failed", "disconnected"].includes(pc.connectionState)
      )
        this.failed();
    };
  }
  private async offer() {
    const pc = this.pc!;
    await pc.setLocalDescription(await pc.createOffer());
    if (pc.iceGatheringState !== "complete")
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          pc.removeEventListener("icegatheringstatechange", changed);
          reject(new Error("Network discovery timed out"));
        }, 15000);
        const changed = () => {
          if (pc.iceGatheringState === "complete") {
            clearTimeout(timer);
            pc.removeEventListener("icegatheringstatechange", changed);
            resolve();
          }
        };
        pc.addEventListener("icegatheringstatechange", changed);
        changed();
      });
    return pc.localDescription!;
  }
  private async route() {
    if (!this.pc) return;
    const stats = await this.pc.getStats();
    let candidate: string | undefined;
    stats.forEach((stat) => {
      if (stat.type === "transport") candidate = stat.selectedCandidatePairId;
    });
    const pair = candidate ? stats.get(candidate) : undefined;
    const relay =
      pair &&
      [
        stats.get(pair.localCandidateId),
        stats.get(pair.remoteCandidateId),
      ].some((s) => s?.candidateType === "relay");
    this.hooks.route?.(this.remote ? (relay ? "Relayed" : "Direct") : "Local");
  }
  async media(
    kind: "camera" | "microphone",
    enabled: boolean,
    facing: "user" | "environment" = "user",
  ) {
    const operation = ++this.mediaGeneration[kind];
    const generation = this.generation;
    const sender = kind === "camera" ? this.camera : this.microphone;
    if (!sender || this.channel?.readyState !== "open")
      throw new Error("Connect to the laptop first");
    this.tracks.get(kind)?.stop();
    this.tracks.delete(kind);
    this.send({ type: "media", kind, enabled: false });
    await sender.replaceTrack(null);
    if (kind === "camera") this.hooks.localCamera?.(null);
    if (!enabled) return;
    if (!navigator.mediaDevices?.getUserMedia)
      throw new Error(
        "Camera and microphone need a trusted HTTPS connection. Use the remote pairing link.",
      );
    const stream = await navigator.mediaDevices.getUserMedia(
      kind === "camera"
        ? {
            video: {
              facingMode: facing,
              width: { ideal: 1280 },
              height: { ideal: 720 },
              frameRate: { ideal: 30, max: 30 },
            },
            audio: false,
          }
        : {
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
            video: false,
          },
    );
    const track = stream.getTracks()[0];
    if (
      generation !== this.generation ||
      operation !== this.mediaGeneration[kind] ||
      this.channel?.readyState !== "open"
    ) {
      stream.getTracks().forEach((value) => value.stop());
      return;
    }
    try {
      await sender.replaceTrack(track);
      this.tracks.set(kind, track);
      this.send({ type: "media", kind, enabled: true });
      if (kind === "camera") this.hooks.localCamera?.(stream);
    } catch (error) {
      track.stop();
      throw error;
    }
  }
  send(message: Input) {
    if (message.type === "move") {
      this.moves[0] += message.dx;
      this.moves[1] += message.dy;
      if (!this.animation)
        this.animation = requestAnimationFrame(() => {
          this.animation = 0;
          this.flush();
        });
    } else {
      this.flush();
      this.write(message);
    }
  }
  private flush() {
    if (this.moves.some(Boolean)) {
      this.write({
        type: "move",
        dx: Math.max(-2000, Math.min(2000, this.moves[0])),
        dy: Math.max(-2000, Math.min(2000, this.moves[1])),
      });
      this.moves = [0, 0];
    }
  }
  private write(message: Input) {
    if (this.channel?.readyState !== "open") return;
    if (this.channel.bufferedAmount > 65536) {
      this.hooks.error(
        "Connection too slow. Reconnecting without replaying input.",
      );
      this.failed();
      return;
    }
    this.channel.send(JSON.stringify(message));
  }
  release() {
    this.send({ type: "release" });
  }
  private error(error: unknown, generation: number) {
    if (generation !== this.generation) return;
    this.hooks.error(
      error instanceof Error ? error.message : "Connection failed",
    );
    this.stop();
    this.hooks.state("disconnected");
  }
  private failed() {
    const reconnect = this.alive && (!this.remote || this.remote.approved);
    this.stop();
    this.hooks.state("disconnected");
    if (reconnect) this.retry = setTimeout(() => this.start(), 2500);
  }
  stop() {
    this.release();
    this.alive = false;
    this.generation++;
    clearTimeout(this.retry);
    clearTimeout(this.timeout);
    clearInterval(this.heartbeat);
    cancelAnimationFrame(this.animation);
    this.animation = 0;
    this.moves = [0, 0];
    this.channel?.close();
    this.pc?.close();
    this.socket?.close();
    for (const track of this.tracks.values()) track.stop();
    this.tracks.clear();
    this.mediaGeneration.camera++;
    this.mediaGeneration.microphone++;
    this.hooks.localCamera?.(null);
    this.pending.clear();
    this.processing = Promise.resolve();
    this.hooks.state("paused");
  }
}
