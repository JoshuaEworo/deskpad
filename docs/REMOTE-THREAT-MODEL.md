# Remote-access threat model

## Trust boundaries

The laptop owner approves phone keys locally. Cloudflare routes signaling and may
relay encrypted media. No remote endpoint can approve or revoke a phone, change
host settings, enable capture devices, run shell commands, or install drivers.
The desktop in-process command bridge is not bound to a network port.

The phone QR pins a laptop public key. A short matching code allows the owner to
compare the request on both screens. Invitations expire after ten minutes, pending
requests after two minutes, connection challenges after one minute. Every phone
request has a signed random nonce and a time window; answers echo request nonces.
SDP fingerprints are signed. Signaling injection and replay should fail closed.

A copied room capability can cause nuisance requests, observe online status, or
consume signaling slots, but cannot control the PC without an approved private
key. Revoke removes a key and disconnects its RTC session. Keys and transport
credentials are not written to console logs. Windows secrets use DPAPI;
non-Windows demo development uses restrictive file permissions, not equivalent
OS-backed protection. Browser private keys are non-extractable IndexedDB keys;
XSS/origin compromise can still use them. HTTPS and strict CSP are required.

## Limits

This is an alpha implementation, not a penetration-test result. Cloudflare hosts
the executable browser client; a compromised hosting account can serve code that
captures keys/media or alters the client. The signed signaling protocol does not
solve a compromised client, laptop, browser extension, or OS user session.

Local HTTP pairing remains trusted-LAN-only. WebRTC media/control is encrypted,
but serving its JavaScript and pairing cookie over HTTP permits an on-path attacker
to replace the client or steal pairing. Never port-forward the local HTTP server.
Remote access uses the separately hosted HTTPS client; it does not tunnel HTTP.

Audio/video are off by default and opt-in on both laptop and phone. Windows media
adapters are not bundled drivers. Testing needs to verify media is stopped, not
just visually unchecked, on disconnect, pause, revoke, and page backgrounding.
Device bridges need virtual-device and echo/routing acceptance checks on Windows.

Public enrollment uses Turnstile plus rate limits. This reduces, not eliminates,
relay abuse. Credential count quotas are not a hard spending cap. Provider API
secrets are scoped to the TURN service and never shipped in a public installer.
Do not embed a shared operator secret in an open-source desktop client.
