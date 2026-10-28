# Wire protocol v1

All routes are on the host's origin. JSON messages have a discriminating `type` and reject unknown fields. Protocol changes require a version bump when old clients would behave incorrectly. No replay queue exists.

## HTTP

| Route | Meaning |
| --- | --- |
| `GET /api/status` | `{protocol:1,demo:boolean,paired:boolean,busy:boolean}` |
| `POST /api/pair` | `{code:"123456"}`; sets an opaque HttpOnly device cookie |
| `POST /api/forget` | Revokes current cookie and removes it |

Mutations require an approved Origin. Bad pair attempts are limited per source and globally. Cookies, screen frames, and credentials must not be logged. Status/auth responses are not cacheable.

## Control

`/ws/control` requires the cookie and an approved Origin. An exclusive lease is assigned before accepting the socket. Successful opening receives `{type:"hello",protocol:1,connection:string,demo:boolean,cursor:[x,y]}`. Competing connections are rejected; browser handshakes may surface rejection as generic code 1006, so the client checks HTTP status.

| Input type | Fields | Semantics |
| --- | --- | --- |
| `move` | `dx,dy`: finite numbers ±2000 | Relative desktop pixels |
| `button` | `button:left/right`, `action:down/up/click` | Owned held button or atomic click |
| `scroll` | `dx,dy`: finite numbers ±100 | Wheel notches; positive y is page downward |
| `text` | `text`: 1–4096 characters | Committed Unicode; no implicit keyboard layout |
| `key` | `key`: allowlisted name; `action:down/up/press` | Named desktop key |
| `shortcut` | `keys`: 1–5 allowlisted names | Press in order, release temporary keys in reverse |
| `release` | none | Release session-owned held inputs |
| `ping` | `timestamp`: finite number | Host echoes `pong` and timestamp |

Key allowlist: Ctrl (`Control`), Alt, Shift, Windows (`Meta`), Enter, Tab, Escape, Backspace, Delete, arrows, Home, End, PageUp/PageDown, a–z, F1–F12. Pointer movement produces `{type:"cursor",position:[x,y]}`. Invalid messages produce `{type:"error",message:string}` and perform no input.

Server receive deadline: eight seconds. Client pings every two seconds. Session finally cleanup releases owned inputs even without a client release message. The client also releases on blur and closes on hidden/pagehide. Stale input is never restored after reconnect.

## Video

`/ws/video?connection=<control-connection-id>` requires both the owning device cookie and active control connection identifier. At most one video socket is admitted.

For each frame:

1. Host sends JSON: `{type:"frame",sequence,width,height,bounds:{left,top,width,height},cursor:[x,y]}`.
2. Host sends one binary JPEG message.
3. Phone decodes, displays the image, then sends the literal text `ack`.
4. Host captures the next fresh frame after the FPS pacing interval.

The host does not capture/send the next frame before acknowledgement. No historical frame queue. Ack timeout closes video; the client reconnects the session. Closing control invalidates its associated video lease. Host and client apply bounded messages/buffers. Metadata bounds are native desktop coordinates; encoded dimensions may be smaller.

## Protocol 2: WebRTC

`POST /api/rtc` accepts `{sdp}` from an origin-checked, cookie-authenticated local
phone and returns an answer. Remote negotiation is carried over the hosted
signaling socket, with P-256 signatures covering exact UTF-8 JSON payload strings.
Signatures are base64url IEEE P1363 r||s, not ASN.1 DER. Device public keys are
P-256 JWKs without private fields. Both sides pin identities before accepting SDP.

Phone requests include `kind`, random `nonce`, Unix `time`, and a signature plus
public key. `pair` additionally carries the short-lived QR invitation. The host
requires explicit approval. `connect` from an approved key yields a signed
`config` containing ICE servers and a one-use, transport-bound challenge. `offer`
must include that challenge; its signed `answer` must echo its request nonce.
Old nonces, expired timestamps, changed signatures, and revoked keys are rejected.

The phone creates an ordered `control` data channel and four transceivers in order:
receive desktop video, receive laptop audio, send phone video, send phone audio.
Existing input message schemas are unchanged. Control messages are bounded to
16 KiB, with a 128-message engine queue and 64 KiB sender backlog cutoff. Desktop
metadata and cursor updates travel over the channel; video has no per-frame ack.
Heartbeats run every two seconds; eight seconds of silence releases the session.
There is a single controller lease across WebSockets and RTC peers.

`hello.media` lists host-permitted media features. Phone capture requires explicit
user action, host opt-in, and trusted HTTPS. Disconnect stops local capture tracks.
`media-status` reports native bridge failures rather than claiming a device exists.

See `cloud/src/index.ts` for room routing. Host socket authorization uses an HTTPS
Bearer credential. Phone authorization uses the `deskpad` subprotocol plus a
`phone.<capability>` subprotocol, never URL query parameters. These credentials
permit signaling, not PC control. TURN credentials are minted only for host-owned,
verified rooms. The TURN API key never leaves the Worker.

Media opt-in messages use `{type:"media",kind:"camera"|"microphone"|"speakers",enabled:boolean}`.
The phone sends explicit opt-out before removing a camera/mic sender track. The
host closes the corresponding sink even when no more media frames arrive. Incoming
media queues are bounded (one video frame, two audio frames); stale frames are
dropped rather than building an ever-growing delay. Laptop loopback capture starts
only while both host permission and phone speaker opt-in are enabled.


A signed `session-ended` host event uses the current `connect` request nonce and
reason `revoked` or `ended`. It is processed immediately, even during ICE gathering.
Revocation removes cached approval and exits controls; the host also rejects future
requests from that key using a nonce-bound signed `error` with `code:access-removed`.
Control transports can send `{type:"session-ended",reason}` before closing.
End session retains pairing but disables automatic reconnect in the current phone
tab (including reloads) until the user chooses Reconnect.

Cloud service `host-online`/`host-offline` events are untrusted availability hints.
They only prompt retries while disconnected: they cannot grant/revoke approval,
change a pinned identity, or interrupt an established peer connection. Every retry
still performs the signed handshake. Invites rotate after ten minutes independently
of existing two-minute pending approvals. The desktop displays the remaining time.
