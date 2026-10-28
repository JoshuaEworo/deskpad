// Deskpad signaling service. No desktop frames or input messages pass through this Worker.
interface Env {
  ROOMS: DurableObjectNamespace;
  ASSETS: Fetcher;
  REGISTRATION_LIMIT: RateLimit;
  REQUEST_LIMIT: RateLimit;
  TURN_ENABLED: string;
  ENROLLMENT_REQUIRED: string;
  TURNSTILE_SITE_KEY?: string;
  TURNSTILE_SECRET_KEY?: string;
  TURN_DAILY_CREDENTIALS?: string;
  BUDGET: DurableObjectNamespace;
  TURN_KEY_ID?: string;
  TURN_API_TOKEN?: string;
}
async function smallBody(request: Request): Promise<string | undefined> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > 4096) {
      await reader.cancel();
      return undefined;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}
const tokenPattern = /^[A-Za-z0-9_-]{43}$/;
const encoder = new TextEncoder();
const hash = async (value: string) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", encoder.encode(value)),
    ),
  )
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
const json = (value: unknown, status = 200) =>
  Response.json(value, { status, headers: { "Cache-Control": "no-store" } });
const security = {
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-src https://challenges.cloudflare.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "Permissions-Policy": "camera=(self), microphone=(self)",
  "Strict-Transport-Security": "max-age=31536000",
};
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (
      url.protocol !== "https:" &&
      !["localhost", "127.0.0.1"].includes(url.hostname)
    ) {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 308);
    }
    // There are no cross-origin API calls. Desktop uses non-browser HTTPS.
    if (
      request.headers.has("Origin") &&
      request.headers.get("Origin") !== url.origin
    )
      return json({ error: "Origin rejected" }, 403);
    if (url.pathname === "/api/config")
      return json({ siteKey: env.TURNSTILE_SITE_KEY || "" });
    if (url.pathname === "/api/status")
      return json({ remoteService: true, paired: false });
    if (url.pathname.startsWith("/api/")) {
      const match =
        /^\/api\/rooms\/([A-Za-z0-9_-]{43})(?:\/(socket|ice|activate))?$/.exec(
          url.pathname,
        );
      if (!match) return json({ error: "Not found" }, 404);
      const source = request.headers.get("CF-Connecting-IP") || "unknown";
      const limit =
        request.method === "PUT" ? env.REGISTRATION_LIMIT : env.REQUEST_LIMIT;
      if (!(await limit.limit({ key: source })).success)
        return json({ error: "Slow down" }, 429);
      if (Number(request.headers.get("Content-Length") || 0) > 4096)
        return json({ error: "Too large" }, 413);
      const id = env.ROOMS.idFromName(match[1]);
      return env.ROOMS.get(id).fetch(request);
    }
    const asset = await env.ASSETS.fetch(request);
    const response = new Response(asset.body, asset);
    for (const [key, value] of Object.entries(security))
      response.headers.set(key, value);
    response.headers.set(
      "Cache-Control",
      url.pathname.startsWith("/assets/")
        ? "public,max-age=31536000,immutable"
        : "no-cache",
    );
    return response;
  },
};

type Registration = {
  owner: string;
  gate: string;
  expires: number;
  verified: boolean;
};
type Attachment = {
  role: "host" | "phone";
  id: string;
  window: number;
  count: number;
};
export class Room implements DurableObject {
  constructor(
    private state: DurableObjectState,
    private env: Env,
  ) {}
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const owner =
      request.headers.get("Authorization")?.replace(/^Bearer /, "") || "";
    const stored = await this.state.storage.get<Registration>("registration");
    const record = stored && stored.expires > Date.now() ? stored : undefined;
    const isHost =
      tokenPattern.test(owner) && record?.owner === (await hash(owner));
    if (
      request.method === "PUT" &&
      !url.pathname.endsWith("/socket") &&
      !url.pathname.endsWith("/ice") &&
      !url.pathname.endsWith("/activate")
    ) {
      if (!tokenPattern.test(owner) || (record && !isHost))
        return json({ error: "Unauthorized" }, 403);
      const text = await smallBody(request);
      if (text === undefined) return json({ error: "Too large" }, 413);
      let body: { gate?: string };
      try {
        body = JSON.parse(text);
      } catch {
        return json({ error: "Invalid JSON" }, 400);
      }
      if (
        !body ||
        typeof body !== "object" ||
        !body.gate ||
        !tokenPattern.test(body.gate)
      )
        return json({ error: "Invalid gate" }, 400);
      const expires = Date.now() + 90 * 86400000;
      const ownerHash = await hash(owner),
        gateHash = await hash(body.gate);
      const enrolled = await this.state.storage.transaction(
        async (transaction) => {
          const current = await transaction.get<Registration>("registration");
          if (
            current &&
            current.expires > Date.now() &&
            current.owner !== ownerHash
          )
            return undefined;
          const verified =
            (current && current.expires > Date.now() && current.verified) ||
            this.env.ENROLLMENT_REQUIRED === "false";
          await transaction.put("registration", {
            owner: ownerHash,
            gate: gateHash,
            expires,
            verified,
          });
          return verified;
        },
      );
      if (enrolled === undefined) return json({ error: "Unauthorized" }, 403);
      await this.state.storage.setAlarm(expires);
      return json({ ok: true, enrollmentRequired: !enrolled });
    }

    if (!record) return json({ error: "Laptop not registered" }, 404);
    if (url.pathname.endsWith("/activate") && request.method === "POST") {
      if (!isHost) return json({ error: "Unauthorized" }, 403);
      if (record.verified) return json({ ok: true });
      const text = await smallBody(request);
      if (text === undefined) return json({ error: "Too large" }, 413);
      let body: { token?: string };
      try {
        body = JSON.parse(text);
      } catch {
        return json({ error: "Invalid JSON" }, 400);
      }
      if (
        !body ||
        typeof body.token !== "string" ||
        body.token.length > 2048 ||
        !this.env.TURNSTILE_SECRET_KEY
      )
        return json({ error: "Verification unavailable" }, 503);
      const result = await fetch(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        {
          method: "POST",
          body: new URLSearchParams({
            secret: this.env.TURNSTILE_SECRET_KEY,
            response: body.token,
            remoteip: request.headers.get("CF-Connecting-IP") || "",
          }),
          signal: AbortSignal.timeout(10000),
        },
      );
      const checked = (await result.json()) as {
        success: boolean;
        action: string;
        hostname: string;
      };
      if (
        !checked.success ||
        checked.action !== "deskpad-enroll" ||
        checked.hostname !== url.hostname
      )
        return json({ error: "Verification failed. Try again." }, 403);
      record.verified = true;
      await this.state.storage.put("registration", record);
      for (const host of this.state.getWebSockets("host"))
        host.send(JSON.stringify({ event: "activated" }));
      return json({ ok: true });
    }
    if (url.pathname.endsWith("/ice") && request.method === "POST") {
      if (!isHost) return json({ error: "Unauthorized" }, 403);
      if (!record.verified)
        return json({ error: "Finish remote setup on your laptop first" }, 403);
      const window = Math.floor(Date.now() / 3600000);
      const count = (await this.state.storage.get<{
        window: number;
        count: number;
      }>("turn")) || { window, count: 0 };
      if (count.window !== window) {
        count.window = window;
        count.count = 0;
      }
      if (++count.count > 12)
        return json({
          iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
          relayUnavailable: true,
        });
      await this.state.storage.put("turn", count);
      if (this.env.TURN_ENABLED !== "true")
        return json({
          iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
        });
      if (!this.env.TURN_KEY_ID || !this.env.TURN_API_TOKEN)
        return json({ error: "Relay not configured" }, 503);
      const budget = this.env.BUDGET.get(this.env.BUDGET.idFromName("daily"));
      if (
        !(await budget.fetch("https://internal/reserve", { method: "POST" })).ok
      )
        return json({
          iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
          relayUnavailable: true,
        });
      const result = await fetch(
        `https://rtc.live.cloudflare.com/v1/turn/keys/${this.env.TURN_KEY_ID}/credentials/generate-ice-servers`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${this.env.TURN_API_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ ttl: 1800 }),
          signal: AbortSignal.timeout(10000),
        },
      );
      if (!result.ok) return json({ error: "Relay unavailable" }, 503);
      const body = (await result.json()) as { iceServers: unknown };
      return json({
        iceServers: Array.isArray(body.iceServers)
          ? body.iceServers
          : [body.iceServers],
      });
    }
    if (
      url.pathname.endsWith("/socket") &&
      request.headers.get("Upgrade")?.toLowerCase() === "websocket"
    ) {
      const protocols = (request.headers.get("Sec-WebSocket-Protocol") || "")
        .split(",")
        .map((v) => v.trim());
      const phoneToken =
        protocols.find((v) => v.startsWith("phone."))?.slice(6) || "";
      const isPhone =
        tokenPattern.test(phoneToken) &&
        record.gate === (await hash(phoneToken));
      if (isPhone && !record.verified)
        return json({ error: "Setup not complete" }, 403);
      if (!isHost && !isPhone) return json({ error: "Unauthorized" }, 403);
      const sockets = this.state.getWebSockets();
      if (sockets.length >= 10) return json({ error: "Room full" }, 429);
      if (isHost)
        for (const socket of this.state.getWebSockets("host"))
          socket.close(1012, "Host reconnected");
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      const role = isHost ? "host" : "phone";
      this.state.acceptWebSocket(server, [role]);
      server.serializeAttachment({
        role,
        id: crypto.randomUUID(),
        window: Date.now(),
        count: 0,
      } satisfies Attachment);
      return new Response(null, {
        status: 101,
        webSocket: client,
        headers: protocols.includes("deskpad")
          ? { "Sec-WebSocket-Protocol": "deskpad" }
          : {},
      });
    }
    return json({ error: "Not found" }, 404);
  }
  webSocketMessage(socket: WebSocket, raw: string | ArrayBuffer) {
    if (typeof raw !== "string" || raw.length > 125000) {
      socket.close(1009, "Message too large");
      return;
    }
    const a = socket.deserializeAttachment() as Attachment;
    if (Date.now() - a.window > 60000) {
      a.window = Date.now();
      a.count = 0;
    }
    if (++a.count > 60) {
      socket.close(1008, "Rate limit");
      return;
    }
    socket.serializeAttachment(a);
    let packet: { to?: string; message?: unknown };
    try {
      packet = JSON.parse(raw);
    } catch {
      socket.close(1008, "Invalid JSON");
      return;
    }
    if (!packet || typeof packet !== "object" || !packet.message) {
      socket.close(1008, "Invalid message");
      return;
    }
    if (a.role === "phone") {
      for (const host of this.state.getWebSockets("host"))
        host.send(JSON.stringify({ from: a.id, message: packet.message }));
    } else {
      for (const phone of this.state.getWebSockets("phone")) {
        if ((phone.deserializeAttachment() as Attachment).id === packet.to)
          phone.send(JSON.stringify(packet.message));
      }
    }
  }
  webSocketClose(
    socket: WebSocket,
    code: number,
    reason: string,
    wasClean: boolean,
  ) {
    const a = socket.deserializeAttachment() as Attachment;
    if (a.role === "phone")
      for (const host of this.state.getWebSockets("host"))
        host.send(JSON.stringify({ left: a.id }));
    socket.close(code === 1006 ? 1000 : code);
  }
  webSocketError(socket: WebSocket) {
    socket.close(1011, "Connection failed");
  }
  async alarm() {
    const record = await this.state.storage.get<Registration>("registration");
    if (!record || record.expires <= Date.now()) {
      for (const socket of this.state.getWebSockets())
        socket.close(1000, "Registration expired");
      await this.state.storage.deleteAll();
    } else await this.state.storage.setAlarm(record.expires);
  }
}

// A service-wide credential issuance cap, independent of per-room/IP limits.
// This is not a guaranteed billing cap: TURN credential expiry is not a byte quota.
export class Budget implements DurableObject {
  constructor(
    private state: DurableObjectState,
    private env: Env,
  ) {}
  async fetch(): Promise<Response> {
    return this.state.blockConcurrencyWhile(async () => {
      const day = Math.floor(Date.now() / 86400000);
      const record = (await this.state.storage.get<{
        day: number;
        count: number;
      }>("budget")) || { day, count: 0 };
      if (record.day !== day) {
        record.day = day;
        record.count = 0;
      }
      const max = Number(this.env.TURN_DAILY_CREDENTIALS || 48);
      if (!Number.isFinite(max) || record.count >= max)
        return json({ error: "Quota reached" }, 429);
      record.count++;
      await this.state.storage.put("budget", record);
      return json({ ok: true });
    });
  }
}
