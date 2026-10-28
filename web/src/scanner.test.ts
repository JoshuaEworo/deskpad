import { afterEach, expect, it, vi } from "vitest";
import { pairingLink } from "./scanner";
afterEach(() => vi.unstubAllGlobals());
it("accepts only Deskpad pairing routes and private LAN host URLs", () => {
  vi.stubGlobal("location", { origin: "https://deskpad.example" });
  for (const url of [
    "https://deskpad.example/#deskpad=abc",
    "http://192.168.1.5:8765/",
    "http://10.1.2.3:8765/",
  ])
    expect(pairingLink(url)).toBe(url);
  for (const url of [
    "javascript:alert(1)",
    "https://evil.example/#deskpad=abc",
    "https://deskpad.example/#setup=secret",
    "http://8.8.8.8:8765/",
    "http://192.168.1.5:80/",
    "https://deskpad.example/?x=1#deskpad=a",
    "https://user:pass@deskpad.example/#deskpad=a",
  ])
    expect(() => pairingLink(url)).toThrow();
});
