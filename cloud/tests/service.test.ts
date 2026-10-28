import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Miniflare } from "miniflare";
import { build } from "esbuild";
let mf: Miniflare;
let configuration: ConstructorParameters<typeof Miniflare>[0];
const room = "a".repeat(43),
  owner = "b".repeat(43),
  gate = "c".repeat(43);
const url = `http://localhost/api/rooms/${room}`;
beforeAll(async () => {
  const bundle = await build({
    entryPoints: ["src/index.ts"],
    bundle: true,
    write: false,
    format: "esm",
    platform: "browser",
  });
  configuration = {
    modules: true,
    script: bundle.outputFiles[0].text,
    compatibilityDate: "2026-08-01",
    durableObjects: { ROOMS: "Room", BUDGET: "Budget" },
    unsafeEphemeralDurableObjects: true,
    bindings: { TURN_ENABLED: "false", ENROLLMENT_REQUIRED: "false" },
    ratelimits: {
      REGISTRATION_LIMIT: {
        namespace_id: "1001",
        simple: { limit: 1000, period: 60 },
      },
      REQUEST_LIMIT: {
        namespace_id: "1002",
        simple: { limit: 1000, period: 60 },
      },
    },
  };
  mf = new Miniflare(configuration);
});
afterAll(async () => {
  await mf?.dispose();
});
describe("signaling authorization", () => {
  it("registers with a high entropy owner, rejects takeover and cross origin requests", async () => {
    expect(
      (
        await mf.dispatchFetch(url, {
          method: "PUT",
          headers: { Authorization: `Bearer ${owner}` },
          body: JSON.stringify({ gate }),
        })
      ).status,
    ).toBe(200);
    expect(
      (
        await mf.dispatchFetch(url, {
          method: "PUT",
          headers: { Authorization: `Bearer ${gate}` },
          body: JSON.stringify({ gate }),
        })
      ).status,
    ).toBe(403);
    expect(
      (
        await mf.dispatchFetch(url + "/ice", {
          method: "POST",
          headers: {
            Origin: "https://evil.example",
            Authorization: `Bearer ${owner}`,
          },
        })
      ).status,
    ).toBe(403);
    expect(
      (await mf.dispatchFetch(url + "/ice", { method: "POST" })).status,
    ).toBe(403);
    const result = await mf.dispatchFetch(url + "/ice", {
      method: "POST",
      headers: { Authorization: `Bearer ${owner}` },
    });
    expect(((await result.json()) as any).iceServers[0].urls).toContain(
      "stun:",
    );
  });
  it("authenticates both socket roles and routes only signaling to the intended phone", async () => {
    expect(
      (
        await mf.dispatchFetch(url + "/socket", {
          headers: { Upgrade: "websocket" },
        })
      ).status,
    ).toBe(403);
    const h = await mf.dispatchFetch(url + "/socket", {
      headers: { Upgrade: "websocket", Authorization: `Bearer ${owner}` },
    });
    const p = await mf.dispatchFetch(url + "/socket", {
      headers: {
        Upgrade: "websocket",
        "Sec-WebSocket-Protocol": `deskpad, phone.${gate}`,
      },
    });
    const host = h.webSocket!,
      phone = p.webSocket!;
    host.accept();
    phone.accept();
    const received = new Promise<any>((resolve) =>
      host.addEventListener(
        "message",
        (e) => resolve(JSON.parse(String(e.data))),
        { once: true },
      ),
    );
    phone.send(
      JSON.stringify({ message: { payload: "signed", signature: "opaque" } }),
    );
    const request = await received;
    expect(request.message.payload).toBe("signed");
    const reply = new Promise<any>((resolve) =>
      phone.addEventListener(
        "message",
        (e) => resolve(JSON.parse(String(e.data))),
        { once: true },
      ),
    );
    host.send(
      JSON.stringify({ to: request.from, message: { payload: "answer" } }),
    );
    expect((await reply).payload).toBe("answer");
    host.close();
    phone.close();
  });
});

it("serializes competing room registrations so only one owner succeeds", async () => {
  const destination = `http://localhost/api/rooms/${"d".repeat(43)}`;
  const responses = await Promise.all(
    [owner, gate].map((secret) =>
      mf.dispatchFetch(destination, {
        method: "PUT",
        headers: { Authorization: `Bearer ${secret}` },
        body: JSON.stringify({ gate }),
      }),
    ),
  );
  expect(responses.map((r) => r.status).sort()).toEqual([200, 403]);
});
it("rejects oversized and malformed registration payloads", async () => {
  const headers = { Authorization: `Bearer ${owner}` };
  expect(
    (
      await mf.dispatchFetch(url, {
        method: "PUT",
        headers,
        body: "x".repeat(5000),
      })
    ).status,
  ).toBe(413);
  expect(
    (await mf.dispatchFetch(url, { method: "PUT", headers, body: "null" }))
      .status,
  ).toBe(400);
});
it("enforces the service-wide relay credential budget", async () => {
  const namespace = await mf.getDurableObjectNamespace("BUDGET");
  const stub = namespace.get(namespace.idFromName("budget-test"));
  for (let i = 0; i < 48; i++)
    expect(
      (await stub.fetch("https://internal/reserve", { method: "POST" })).status,
    ).toBe(200);
  expect(
    (await stub.fetch("https://internal/reserve", { method: "POST" })).status,
  ).toBe(429);
});
it("requires human enrollment before a public room accepts phones or mints ICE config", async () => {
  await mf.setOptions({
    ...configuration,
    bindings: { TURN_ENABLED: "false", ENROLLMENT_REQUIRED: "true" },
  });
  const destination = `http://localhost/api/rooms/${"e".repeat(43)}`;
  const headers = { Authorization: `Bearer ${owner}` };
  const result = await mf.dispatchFetch(destination, {
    method: "PUT",
    headers,
    body: JSON.stringify({ gate }),
  });
  expect(((await result.json()) as any).enrollmentRequired).toBe(true);
  expect(
    (await mf.dispatchFetch(destination + "/ice", { method: "POST", headers }))
      .status,
  ).toBe(403);
  expect(
    (
      await mf.dispatchFetch(destination + "/socket", {
        headers: {
          Upgrade: "websocket",
          "Sec-WebSocket-Protocol": `deskpad, phone.${gate}`,
        },
      })
    ).status,
  ).toBe(403);
  expect(
    (
      await mf.dispatchFetch(destination + "/activate", {
        method: "POST",
        headers,
        body: JSON.stringify({ token: "fake" }),
      })
    ).status,
  ).toBe(503);
});
