import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RtcConnection } from "./rtc-connection";
import type { Hooks } from "./connection";
import type { RemoteConfig } from "./remote-identity";
const identities = vi.hoisted(() => ({ forget: vi.fn(), save: vi.fn() }));
vi.mock("./remote-identity", () => ({
  nonce: () => crypto.randomUUID(),
  phoneKeys: async () => ({}),
  sign: async (_: unknown, value: unknown) => value,
  verify: async (value: unknown) => value,
  saveRemote: identities.save,
  forgetRemote: identities.forget,
}));
class Socket {
  static OPEN = 1;
  static all: Socket[] = [];
  readyState = 1;
  sent: { nonce: string; kind: string }[] = [];
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: () => void;
  constructor() {
    Socket.all.push(this);
  }
  send(raw: string) {
    this.sent.push(JSON.parse(raw).message);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  receive(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) });
  }
}
let hooks: Hooks;
let config: RemoteConfig;
let connection: RtcConnection;
const flush = async () => {
  for (let i = 0; i < 12; i++) await Promise.resolve();
};
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  Socket.all = [];
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("location", { origin: "https://deskpad.example" });
  vi.stubGlobal("localStorage", { getItem: () => "My phone" });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  hooks = {
    state: vi.fn(),
    error: vi.fn(),
    frame: vi.fn(),
    cursor: vi.fn(),
    latency: vi.fn(),
    ended: vi.fn(),
    progress: vi.fn(),
  };
  config = {
    v: 2,
    room: "room",
    gate: "gate",
    host: {},
    name: "Laptop",
    approved: true,
  };
  connection = new RtcConnection(hooks, config);
});
afterEach(() => {
  connection.stop();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
async function open() {
  connection.start();
  await flush();
  const socket = Socket.all.at(-1)!;
  socket.onopen?.();
  await flush();
  return socket;
}
it("signed access removal ejects the phone and never automatically reconnects", async () => {
  const socket = await open();
  socket.receive({
    kind: "error",
    nonce: socket.sent[0].nonce,
    code: "access-removed",
    message: "Access removed",
  });
  await flush();
  await vi.advanceTimersByTimeAsync(60000);
  expect(identities.forget).toHaveBeenCalledOnce();
  expect(hooks.ended).toHaveBeenCalledWith("revoked");
  expect(Socket.all).toHaveLength(1);
});
it("host events must match this connection's nonce", async () => {
  const socket = await open();
  socket.receive({
    kind: "session-ended",
    nonce: "old-session",
    reason: "revoked",
  });
  await flush();
  expect(identities.forget).not.toHaveBeenCalled();
  expect(hooks.ended).not.toHaveBeenCalled();
});
it("End session retains pairing and suppresses reconnect until another start", async () => {
  const socket = await open();
  socket.receive({
    kind: "session-ended",
    nonce: socket.sent[0].nonce,
    reason: "ended",
  });
  await flush();
  await vi.advanceTimersByTimeAsync(60000);
  expect(hooks.ended).toHaveBeenCalledWith("ended");
  expect(identities.forget).not.toHaveBeenCalled();
  expect(Socket.all).toHaveLength(1);
  await open();
  expect(Socket.all).toHaveLength(2);
});
it("temporary host errors retry, and stopping cancels the retry", async () => {
  const socket = await open();
  socket.receive({
    kind: "error",
    nonce: socket.sent[0].nonce,
    message: "Laptop is already in use",
  });
  await flush();
  await vi.advanceTimersByTimeAsync(2500);
  await flush();
  expect(Socket.all).toHaveLength(2);
  connection.stop();
  await vi.advanceTimersByTimeAsync(60000);
  expect(Socket.all).toHaveLength(2);
});
