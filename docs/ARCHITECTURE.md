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
| `trackpad-surface.ts` | Shared pointer binding and cancellation for the portrait pad and landscape desktop |
| `keyboard.ts` | Native phone input and composition handling |
| `viewer.ts` | Width-based desktop fitting, content-aware pan bounds, pinch zoom, resize preservation |
| `main.ts` | UI state, compact layout, settings, session orchestration |

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

VisualViewport events size the app to the space actually visible above the native keyboard. This does not rely on the Chromium-only VirtualKeyboard API. A real focusable 16px contenteditable input sink accepts native text without occupying a visible typing row. Composition stays local until commit; paste is handled as plaintext. Pairing transfers focus synchronously during the Connect gesture, before network awaits. A previously paired page offers a single keyboard tap because Safari does not guarantee software-keyboard opening without a user gesture. Native keyboard behavior must still be tested on physical iOS.

The desktop viewer derives its base dimensions from width only. A shorter keyboard-visible viewport clips/pans the viewer if necessary, rather than shrinking its width or clearing zoom. Pan bounds use the actual scaled image dimensions. Trackpad height is a separate pixel preference (default 80px), capped on short viewports; old percentage-based screen sizing is intentionally not reused. The connected layout has no header, status row, visible input box, or footer. Tiny branding/status and a Settings entry overlay the desktop. Settings is a separate full-viewport tabbed view with safe-area navigation and a scrolling panel. Quick actions share the hotkey bar; optional mouse/scroll controls are preferences in the Pointer tab. An optional scroll wheel occupies a 40px rail beside the trackpad, sharing its height; it preserves keyboard focus and uses the same natural-scroll direction. Pointer speed defaults to 4× with a 2.5×–7× range. Existing speeds below the new minimum migrate to 4×; valid saved speeds remain unchanged.

Two-finger viewer gestures snapshot the initial midpoint, distance, zoom, and pan. Each move maps the same image point to the current midpoint, allowing focal zoom and two-finger panning. Computing from the gesture start avoids drift from sequential per-finger events and intermediate edge clamping. Final pan is constrained to image bounds.

Trackpad gestures own a complete touch sequence. When one finger remains after a two-finger gesture, it cannot turn into a cursor movement or click. Cancellation releases a drag. Portrait screen gestures belong to the viewer, separate from the trackpad. Landscape explicitly routes the desktop surface to either the relative-trackpad binding (Mouse) or the viewer (View), never both. View mode cannot generate host pointer input. Preferences persist only locally on the phone.

## Landscape and orientation

Orientation follows Screen Orientation API changes, with a legacy angle/screen-dimension fallback. VisualViewport changes do not decide orientation: opening a software keyboard must not activate landscape. Browser tests simulate portrait keyboard-sized viewports with fixed physical screen orientation rather than rotating the test device accidentally.

Landscape removes the portrait pad, divider, mouse-button row, and overlay branding/menu. The desktop uses contain fitting above a normal-flow dock; image proportions are preserved and controls never overlap it. The expanded dock is 42px high; the collapsed rail is 28px. Safe-area padding remains outside the viewer/dock. The collapsed rail retains branding/status, Mouse/View, keyboard, and expand controls. Expanded branding is in the menu. Collapse preference is persisted locally.

The shared trackpad recognizer binds to the portrait pad or the entire landscape screen, depending on layout and selected mode. DesktopViewer has an explicit enabled flag: disabled in landscape Mouse mode, enabled in View mode and portrait. Mode changes, rotation, and collapsing the dock cancel pending contacts/hold timers and release remote held keys/buttons. Viewer zoom/pan state is stored separately for each orientation within the session. Portrait keyboard intent is remembered on entry to landscape; landscape initially dismisses it, and return to portrait attempts focus restoration without claiming that iOS permits automatic software keyboard activation.

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


## Desktop and WebRTC architecture (0.2 alpha)

`desktop.py` owns Qt and the tray on the main thread. `Engine` runs Uvicorn on a
separate thread. `Service` synchronizes snapshots and schedules commands on the
engine loop; it exposes no HTTP administration. Settings are validated and saved
atomically. `RtcHub` shares the existing controller lease and serialized input
worker with the WebSocket server. `Peer` bounds control queues, handles heartbeat
timeouts, and releases all held input before dropping its lease.

`Identity` persists P-256 keys and approved-device public keys. `Remote` makes
outbound HTTPS/WSS connections and verifies signed requests before creating a peer.
The cloud Worker routes opaque signaling through one hibernatable Durable Object
per host. A separate Budget object serializes service-wide relay issuance limits.
Cloud credentials remain in Worker secrets. The browser uses non-extractable
IndexedDB signing keys, pinned host keys, and nonce-checked responses.

`session.ts` selects RTC or legacy JPEG. `RtcConnection` handles negotiation,
media track switching, bounded input, and reconnect. `DesktopViewer` and gesture
code are unchanged. `media_devices.py` isolates Windows virtual camera/audio and
loopback adapters; host and phone must independently opt in. Native-device
distribution remains a release gate, rather than a fake successful toggle.


## Display routing and hover stability

Capture owns topology detection, selection and MSS lifetime on its single worker.
Topology refreshes every two seconds so a removed display falls back safely.
Frame metadata carries the active display and its bounds. Automatic following
chooses the display containing the physical cursor and never moves that cursor.
An explicit phone selection validates the detected display on the capture worker,
then focuses it once on the input worker if the cursor is outside its bounds.
A short handoff grace period prevents capture from switching back before focus.
DXGI remains limited to an unambiguous single-output mapping; other layouts use MSS.

Windows movement accumulates fractional deltas and skips SetCursorPos entirely
when no integer movement is needed. Gesture filtering compares against the last
emitted position, allowing slow intentional travel to accumulate. A long-press
can begin a drag only if no cursor movement has been emitted since contact began.
Heartbeat and video metadata only read cursor position. Browser overlay updates
never force a saved absolute cursor position onto Windows.
