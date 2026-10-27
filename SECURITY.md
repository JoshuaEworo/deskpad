# Security scope

Deskpad alpha is for one owner's devices on a trusted private LAN. It gives a paired phone screen visibility and input control over the user's desktop session. Do not expose the port to the internet, guest/public Wi-Fi, or an untrusted LAN.

The current HTTP/WebSocket transport is **not encrypted**. Pairing and Origin/Host validation do not protect against a network observer, compromised router, or malicious trusted-network peer intercepting bearer credentials. Remote internet access and production HTTPS onboarding are not implemented.

The QR code includes only the connection address. The host console displays a random six-digit pairing code. Successful pairing creates an opaque expiring device credential stored in an HttpOnly SameSite=Strict cookie; the host stores only its hash and expiry. Failed pairing attempts are rate limited. One controller lease owns all held input; closing/losing it triggers cleanup.

To stop sharing, stop the host with Ctrl+C. To revoke remembered phones, stop the running host, then run `deskpad --forget-devices`. The phone's Forget action revokes that phone. Keep the host unelevated; secure desktop/UAC control is not supported.

Local credential hashes live under `%LOCALAPPDATA%\Deskpad\devices.json` on Windows. Normal logging excludes screen data, typed text, tokens, and access URLs. The pairing code is deliberately visible in the host console; do not post screenshots of it.

Until this repository has a dedicated private reporting contact, use GitHub's private vulnerability reporting if enabled. Do not publish a working exploit or credentials in a public issue. For non-sensitive scope/documentation questions, a normal issue is fine.
