import { afterEach, expect, it, vi } from "vitest";
import { gatherIce, usableIceServers } from "./rtc-network";

function peer(sdp = "") {
  return Object.assign(new EventTarget(), {
    iceGatheringState: "gathering",
    signalingState: "have-local-offer",
    localDescription: { sdp },
  });
}
afterEach(() => vi.useRealTimers());
it("keeps UDP, TCP and TLS fallback routes while removing blocked port 53", () => {
  expect(
    usableIceServers([
      {
        urls: [
          "turn:turn.cloudflare.com:53?transport=udp",
          "turns:turn.cloudflare.com:443?transport=tcp",
        ],
        username: "short-lived",
        credential: "test",
      },
      { urls: "stun:stun.cloudflare.com:3478" },
      { urls: "turn:turn.cloudflare.com:53" },
    ]),
  ).toEqual([
    {
      urls: ["turns:turn.cloudflare.com:443?transport=tcp"],
      username: "short-lived",
      credential: "test",
    },
    { urls: ["stun:stun.cloudflare.com:3478"] },
  ]);
});
it("uses collected candidates when an unused relay transport stalls discovery", async () => {
  vi.useFakeTimers();
  const pc = peer("v=0\r\na=candidate:1 1 udp 1 192.0.2.1 1234 typ relay\r\n");
  const result = gatherIce(pc as unknown as RTCPeerConnection);
  await vi.advanceTimersByTimeAsync(15000);
  await expect(result).resolves.toBeUndefined();
  expect(vi.getTimerCount()).toBe(0);
});
it("reports failure if discovery timed out without any candidates", async () => {
  vi.useFakeTimers();
  const result = expect(
    gatherIce(peer() as unknown as RTCPeerConnection),
  ).rejects.toThrow("No network route found");
  await vi.advanceTimersByTimeAsync(15000);
  await result;
});
it("finishes early when discovery completes and cancels on peer shutdown", async () => {
  vi.useFakeTimers();
  const pc = peer();
  const result = gatherIce(pc as unknown as RTCPeerConnection);
  pc.iceGatheringState = "complete";
  pc.dispatchEvent(new Event("icegatheringstatechange"));
  await expect(result).resolves.toBeUndefined();
  expect(vi.getTimerCount()).toBe(0);
  pc.iceGatheringState = "gathering";
  const cancelled = gatherIce(pc as unknown as RTCPeerConnection);
  pc.signalingState = "closed";
  pc.dispatchEvent(new Event("signalingstatechange"));
  await expect(cancelled).rejects.toThrow("cancelled");
  expect(vi.getTimerCount()).toBe(0);
});
