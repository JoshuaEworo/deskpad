# Architecture

## Product boundary

Deskpad controls an already-running Windows desktop from a portrait iPhone. The primary interaction is relative pointer movement on a separate trackpad, with a visible desktop above. The existing Windows session, apps, files, and focus remain the source of truth.

The first release is a LAN tool, not a hosted service or gaming client. One process serves the static phone UI, pairing endpoints, control socket, and video socket. There is no database server, message broker, frontend framework, or cloud component.

## Structure and ownership

| Module | Responsibility |
| --- | --- |
| `host/deskpad/cli.py` | Host configuration, DPI awareness, address selection, QR and pairing display |
| `auth.py` | Pair code, rate limits, hashed remembered credentials, expiration/revocation |
| `protocol.py` | Input schema and bounds; no arbitrary native function calls |
| `server.py` | HTTP and WebSocket lifecycle, exclusive controller lease, backpressure |
| `input.py` | Held-input ownership, shortcuts, idempotent cleanup |
| `native.py` | Windows SendInput/cursor API boundary and harmless demo backend |
| `capture.py` | MSS capture, downscale/encode, synthetic demo frames |
| `web/src/connection.ts` | Transport, heartbeat, reconnect, input ordering/coalescing |
| `gestures.ts` | DOM-independent trackpad gesture state machine |
| `keyboard.ts` | Native phone input and composition handling |
| `main.ts` | UI state, viewer transforms, settings, session orchestration |

## Connections and latency

After pairing, the phone opens an authenticated control WebSocket. The host grants a single lease and returns a random connection identifier. The video socket must present the same device cookie and connection ID. A second tab cannot take over an active lease. The socket is the owner of remote held inputs, not just the device cookie.

Video uses its own socket. Each iteration captures one fresh frame, sends its metadata and JPEG, then waits for the phone's decode/display acknowledgement before capturing the next. There is no frame history. Capture/encoding run on a dedicated single worker thread because MSS state belongs to its creating thread. A configured FPS cap is a ceiling, not a guaranteed rate.

Control input uses a separate socket, with pointer deltas coalesced once per animation frame. Pending motion flushes before button transitions, preventing a button-up from overtaking the last drag movement. Control socket buffer growth stops the connection rather than replaying seconds of stale input. Reconnect never replays input or restores held modifiers.

Native input work is sequential within the control receive loop and offloaded from the ASGI loop. Only the leased session injects input. Cleanup releases owned keys/buttons on disconnect, timeout, hidden-page teardown, and explicit release. The host heartbeats have an eight-second receive deadline; the browser pings every two seconds. The lease is not available until cleanup completes.

The phone overlays the pointer using host cursor coordinates, normalized against captured monitor bounds. Cursor updates come from control responses and frame metadata. This handles physical mouse movement too; pointer shapes are not captured.

## Windows boundary

DPI awareness is enabled before capture/input, so cursor coordinates and pixel bounds share a coordinate space on scaled monitors. Mouse deltas move the actual Windows cursor. Button/scroll/key input uses correctly sized Windows INPUT unions including ULONG_PTR. Text uses UTF-16 Unicode packets; shortcuts use virtual keys. The app never guesses a user's physical keyboard layout for text.

Native calls are intentionally narrow. No shell, process launch, arbitrary hotkey codes, or file access is exposed to the phone. Elevated apps/secure desktops are outside scope. Demo mode provides protocol/UI verification, not evidence of native Windows correctness.

## iPhone interaction

VisualViewport events size the app to the space actually visible above the native keyboard. This does not rely on the Chromium-only VirtualKeyboard API. The typing field is real, focusable, and 16px to avoid small-input Safari zoom. Composing text stays local until composition commit. Native keyboard behavior must still be tested on physical iOS.

Trackpad gestures own a complete touch sequence. When one finger remains after a two-finger gesture, it cannot turn into a cursor movement or click. Cancellation releases a drag. Screen gestures belong to the viewer, not the trackpad; they can never generate host pointer input. Preferences persist only locally on the phone.

## Pairing and privacy

The QR contains the address only. A six-digit code is shown in the host console, generated on startup. Pairing issues an opaque 256-bit device token in an HttpOnly SameSite=Strict cookie, with only its SHA-256 digest and expiration persisted. Device tokens expire in 30 days. Forget revokes the current phone; CLI revokes all phones. Pair attempts are rate limited. Origin/Host checks narrow browser cross-origin and DNS-rebinding exposure. No CORS wildcard.

LAN HTTP remains plaintext. This is an explicit alpha limitation, not a claim of secure remote internet access. Device cookies are bearer credentials on that trusted LAN. The future HTTPS deployment strategy must include usable iPhone certificate trust and documented bootstrap; silently shipping self-signed warnings is not an acceptable substitute.

## Decisions and growth

- Python/FastAPI: fast Windows iteration, explicit protocol schemas, easy platform isolation. Native Windows integration is testable without importing user32 on Linux.
- TypeScript/Vite with direct DOM: small shipped client, no framework state model to coordinate pointer frames. Gesture/keyboard/transport modules remain independently testable.
- JPEG first: validate ergonomics and collect real measurements before committing to codec complexity. Capture can later become a Media Foundation/DXGI pipeline; video transport can become WebRTC. Control semantics should remain stable.
- No service worker: keep authenticated screen data uncached, avoid stale phone/host versions, and acknowledge LAN HTTP restrictions.
- MIT: permissive reuse for the public project; dependencies retain their own licenses.

Before adding WebRTC, measure input RTT, encode/decode time, text readability, and network throughput on target hardware. Before a stable public release, complete the device matrix and resolve the outstanding input/viewport bugs in the testing checklist.
