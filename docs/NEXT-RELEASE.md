# Desktop and remote-access release

This is an implementation work log, not a claim of deployed functionality.

## Design

Keep the existing phone controls. A styled PySide6 desktop shell supervises the
FastAPI engine on its own event-loop thread; admin operations cross an in-process
command boundary, never a LAN/cloud HTTP admin endpoint. Closing the window hides
it only when a tray is available. Quitting stops peers and releases input.

Cloudflare Workers serves the phone assets. A Durable Object per laptop routes
signaling only; Cloudflare TURN provides optional relay. The laptop makes outbound
HTTPS/WSS connections. The server never receives screen frames for direct peers.

A QR fragment pins the host P-256 public key and carries a random room capability.
Fragments are removed from the address bar immediately. A phone generates a key,
requests approval, and shows a short matching verification code. The laptop owner
must explicitly approve it. Every subsequent handshake is signed and challenge-bound;
the SDP fingerprints are covered by signatures. A room capability grants signaling
access only, never permission to control the PC. Revoked keys cannot create peers.
The service can deny service, observe connection metadata, or deliver a malicious
web client if compromised: a browser-delivered client is not protection against a
compromised hosting origin. Do not claim otherwise.

WebRTC carries desktop video, cursor metadata, control, and optional phone camera,
phone microphone, and system audio. Input stays ordered and bounded; stale queues
close the peer and release all held keys/buttons. One controller across LAN and RTC.

## Delivery gates

- [x] Desktop lifecycle, pairing UI, device revocation, settings and installer source
- [x] Windows CI builds the desktop executable and smoke-tests rendering/shutdown
- [ ] Installer installation/uninstallation verified on a physical Windows machine
- [x] Signed pairing, replay tests, explicit approval, revocation
- [x] Worker routing, authentication, rate and size limits, TURN credentials
- [x] Desktop RTC capture/control and reconnect browser tests
- [x] Phone media controls and adapters for installed Windows virtual devices
- [ ] Bundled Deskpad Camera/Microphone devices without external device setup
- [x] Cloudflare service deployed; native cellular acceptance remains pending
- [ ] Native Windows, iPhone Safari, cellular and forced-relay acceptance
- [x] Signed update metadata verification, bounded downloads and installer handoff source
- [x] Update signing key and public alpha channel, signature/digest verified
- [ ] Physical Windows upgrade acceptance
- [ ] Signed installer / signed virtual device distribution

Media Foundation camera and audio-driver integration require native Windows testing.
Existing installed virtual-device backends may be supported for development, but
must not be presented as bundled Deskpad devices. Driver signing and distribution
are a separate release gate. Software video encoding must not be called hardware
encoding without a verified hardware backend.

## Validation in this workspace

- Python authorization, schema, input cleanup, identity persistence, tampering,
  replay, clock expiry, approval, challenge binding, and revocation tests pass.
- Chromium: original portrait/landscape controls, RTC video/input, signed remote
  pairing/reconnect, and fake camera/mic streaming plus disconnect cleanup pass.
- Miniflare runs the actual Worker for owner authentication, socket routing,
  concurrent registration, oversized/malformed requests, enrollment gating and
  shared relay-issuance budgets. This does not validate live TURN or Turnstile.
- Qt offscreen demo launches, renders the desktop window, and shuts down its host.
- Cloudflare service is deployed at https://deskpad.eworojoshua.workers.dev.
- Signed alpha 0.2.0-alpha.2 is published; no physical upgrade success is claimed.
- No physical Windows capture/input, iPhone Safari media routing, hardware encoder,
  native device installer, signed binary, or real Zoom call is claimed tested.
