# Deskpad hosted service

Cloudflare Worker + SQLite Durable Objects + optional Cloudflare Realtime TURN.
The phone client is the existing Vite build. No VPS, router setup, or VPN app.
No live deployment, domain, or Cloudflare credentials are included in the repo.

## Deploy

1. Create a Cloudflare account and a Turnstile widget for the intended Worker
   hostname. Use managed mode; keep its secret private.
2. From the repository root, build the phone assets:
   `npm ci --prefix web` then `npm run build --prefix web`.
3. `cd cloud`, `npm ci`, then `npx wrangler login`.
4. Add `TURNSTILE_SITE_KEY` to `vars` in `wrangler.jsonc` (public widget key).
   Run `npx wrangler secret put TURNSTILE_SECRET_KEY`.
5. `npm run deploy`. Copy the HTTPS workers.dev origin into desktop Settings.
   A paid domain is optional. Test local/remote pairing before enabling TURN.
6. Create a Realtime TURN key in Cloudflare. Store `TURN_KEY_ID` and
   `TURN_API_TOKEN` with `wrangler secret put`; never in GitHub or the client.
   Set `TURN_ENABLED` to `true`, then redeploy.
7. Desktop → Anywhere → Finish remote setup. Complete Turnstile in the laptop's
   browser once, return to Deskpad, scan the QR on the phone, and approve its code.

Public installers should supply the hosted origin at build time through a bundled
`deployment.json`. Ordinary users should not edit the service URL. The editable
field remains useful for self-hosters; no active hosted URL is assumed here.

## Limits and security

- All service URLs must be HTTPS. Cross-origin browser requests are rejected.
- Room IDs and owner/gate credentials are independently random 256-bit values.
- Room owner credentials are hashed at rest in the Durable Object. The gate is also
  hashed. Phone socket capability is not a PC-control credential.
- Human verification is required for public room activation. Do not disable
  `ENROLLMENT_REQUIRED` on a public deployment. The false setting is for tests.
- Per-IP registration/request limits, ten sockets per room, 60 signaling messages
  per socket per minute, 125 KB message limit, and host replacement cleanup.
- TURN issuance: 12 requests/room/hour and a separate service-wide daily cap
  (`TURN_DAILY_CREDENTIALS`, default 48). Short-lived credentials last 30 minutes.
  These are abuse controls, **not a guaranteed monetary or byte cap**. Credential
  expiry is not a guaranteed termination of an existing allocation. Monitor usage
  and provider billing; disable TURN to stop issuing new credentials if needed.
- Signaling is metadata-visible. It carries signed SDP, not desktop images.
  TURN relays encrypted DTLS/SRTP. The hosting origin serves executable client code:
  if that origin is compromised, the browser client is compromised too.
- No analytics or request logging is enabled in the Worker config. Do not turn on
  header/body logging that could record credentials, SDP, or setup fragments.
- Idle room registrations expire after 90 days; the laptop renews on reconnect.
- Back up the laptop's Deskpad state if device continuity matters. Windows protects
  its identity/transport secrets using user-scoped DPAPI. A changed host key must
  never be silently accepted by a phone.

## Test

`npm run check` and `npm test` run type checks and real workerd/Miniflare integration
checks. Test live staging with home Wi-Fi ↔ cellular, forced relay, offline host,
resume from sleep, revoked device, and TURN outage before opening a public service.
The synthetic browser signaling harness is not a live Cloudflare acceptance test.
