# Deskpad

**Your desktop above. Your controls below.**

Deskpad connects a Windows laptop to your phone. View the desktop at the top,
move its cursor with a trackpad, and type with the phone’s keyboard. It is free,
open source, and designed around a phone held comfortably in your hands.

**0.2 is a development alpha.** Desktop UI and WebRTC work in automated tests;
this is not a verified public remote-access or Zoom-device release. See the
[remaining release gates](docs/NEXT-RELEASE.md).

## What works in the source implementation

- Styled Windows desktop companion with QR pairing, system tray, pause/disconnect,
  approved-device revocation, optional launch at login and keep-awake.
- Existing portrait phone UI, keyboard-first controls, focal pinch zoom, optional
  scroll wheel, and landscape Mouse/View modes with a docked, collapsible hotkey bar.
- WebRTC desktop video, cursor updates, bounded ordered input, and reconnect.
  JPEG/WebSocket compatibility transport remains available.
- Cloudflare signaling-service source with pinned device keys, signed negotiation,
  explicit laptop approval, replay protection, verified enrollment, and TURN fallback.
- Opt-in phone camera/mic transport and laptop audio playback. Native adapters use
  **installed virtual camera/audio devices**, not bundled Deskpad devices. Desktop
  setup checks, guided instructions and phone-side status explain what is ready;
  see [camera and audio setup](docs/MEDIA.md).
- Windows executable/installer build and CI smoke test for desktop render/shutdown.

## Install / run

Start at [the Deskpad website](https://deskpad.eworojoshua.workers.dev) to download the Windows installer or connect your phone. Downloads come from [GitHub Releases](https://github.com/JoshuaEworo/deskpad/releases).
Quit an existing Deskpad instance from its system tray menu before a manual upgrade.
The desktop app also offers **Settings → App updates** for signed, verified updates.
These are alpha releases; Windows Authenticode signing is not configured yet.

From source, use **Windows 10/11, Python 3.11+, Node.js 20.19+ or 22.12+**:

```powershell
.\scripts\start.ps1
```

The script installs dependencies, builds the phone UI, and opens the desktop app.
For contributors, `-Headless` opens the original CLI; `-Demo` uses a synthetic
screen and records input without controlling the computer.

Manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,desktop,media]" -c requirements.lock
npm ci --prefix web
npm run build --prefix web
.\.venv\Scripts\deskpad-desktop.exe
```

## Connect your phone

**Local only:** open Deskpad, scan its QR, and enter the displayed six-digit code.
Both devices need the same trusted network. Allow private-network access if
Windows Firewall asks. Keep the laptop awake and its display available.

**Anywhere:** official alpha installers include the hosted Deskpad service origin.
Self-hosters can deploy their own [Cloudflare service](cloud/README.md) and enter its
HTTPS origin in Settings. Cloning the repo does not deploy a separate service.
Enable Anywhere, complete the one-time verification in your laptop browser,
scan the QR, compare the code on both screens, and approve the phone on the laptop.
Later connections use the remembered phone key. Direct connections are preferred;
TURN relays encrypted traffic when needed. No VPN app or router setup is required.

The laptop must be awake, online, and running Deskpad. Closing the desktop window
hides it only when a system tray is available; choose Quit to stop the host.
Local-only mode uses the LAN host and does not depend on the hosted service.

In Safari, use **Share → Add to Home Screen** for a convenient shortcut. On an
already-paired page, a keyboard-button tap may be needed to show the native
keyboard. There is no offline service worker.

## Controls

| Action | Gesture or button |
| --- | --- |
| Move pointer | One finger on trackpad |
| Left click | Tap, or left mouse button |
| Right click | Two-finger tap, or right mouse button |
| Scroll | Two fingers, or enable the side scroll wheel in Settings → Pointer and drag it with one finger; reverse direction in settings |
| Drag | Hold still briefly, then move; double-tap and drag also works |
| Persistent drag | Control bar → Quick actions → Drag lock; opening Settings releases held input |
| Zoom desktop | Portrait: pinch the screen. Landscape: select View, then pinch around the part you want to enlarge |
| Pan desktop | Portrait: drag the screen while zoomed. Landscape: select View, then drag |
| Type | Keyboard stays focused while using the trackpad/desktop keys; bottom-right button shows/hides it |
| Shortcut | Select Ctrl/Alt/Shift/Win, then a letter or desktop key; modifiers release afterward |
| Paste phone text | Control bar → Quick actions → Send text; paste or dictate, then send |
| Paste laptop clipboard | Control bar → Quick actions → Paste on PC |

Portrait keeps a separate trackpad beneath the screen. Landscape hides that trackpad and fits the entire desktop above a docked control bar; the bar never overlays the image. In **Mouse** mode, sliding over the desktop moves the real Windows cursor, and tapping clicks at the cursor position (not at the finger position). Two-finger tap right-clicks, two fingers scroll, and hold/double-tap drag works as on the portrait pad. In **View** mode, screen gestures only pan/zoom the viewer and send no mouse input. Switching modes releases held inputs.

The landscape bar collapses to a shorter rail with small branding, Mouse/View controls, a keyboard button, and an expand button. Collapse state is remembered. Landscape starts with the keyboard tucked away; open it explicitly when needed. Rotating back restores the portrait view and trackpad preferences, and attempts to restore keyboard focus if it was previously open. Safari may require a keyboard tap after rotation. Each orientation keeps its own in-session zoom/pan state.

The phone's Settings page has Pointer, Display, Media and Session tabs. Its back
controls stay visible while the active panel scrolls. Use the grid icon on the
control bar to switch between desktop keys and quick actions; those actions do
not live in Settings. Manage paired-phone access from Devices on the laptop.

Displays are detected automatically. With multiple displays, a selector appears
beside the keyboard button. Selecting a display moves an off-screen cursor into
that display once; otherwise Deskpad only observes the physical cursor. Settings
→ Display can disable automatic cursor-follow to keep viewing the selected screen.

## Camera and audio

Enable permissions in desktop Settings, then toggle each feature in phone Settings → Media. Phone camera/mic access requires a trusted HTTPS origin and browser consent.
Front/back camera switching and an optional preview are available in Settings → Media.
Disconnecting stops phone capture. Audio/video queues are bounded so slow sinks
do not accumulate historical frames.

- **Camera:** the development adapter uses pyvirtualcam with an installed supported
  virtual camera, such as OBS Virtual Camera. It does not create a Deskpad-branded
  Windows camera by itself.
- **Microphone:** choose the output side of an installed virtual audio cable in
  desktop Settings; choose that cable’s recording endpoint in Zoom. Do not choose
  physical speakers, which would play your microphone aloud. Changed device
  identities fail closed and require reselection.
- **Speaker:** host loopback capture starts only when permitted on the laptop and
  enabled on the phone. Real iPhone routing and echo behavior need device testing.

Bundled native devices, signing, clean-machine installation, and real Zoom calls
remain release work. No automatic third-party driver downloads are performed.

## Performance and security

WebRTC removes the legacy JPEG per-frame acknowledgement round trip. Encoding is
currently software-based. GPU capture is attempted on a single-display Windows
machine, with MSS fallback and explicit MSS selection on multi-display machines.
Do not infer a latency guarantee from frame-rate settings or input RTT. Hardware
encoding, adaptive-resolution tuning, and physical end-to-end measurements remain
validation work.

Local pairing/UI delivery uses HTTP and is **trusted-LAN-only**. WebRTC encryption
does not protect JavaScript delivered over HTTP from an on-path attacker. Never
port-forward the local HTTP server. Internet access uses a separate HTTPS client,
signed device negotiation, and encrypted WebRTC transport.

One controller owns input at a time across both transports. Queue limits,
heartbeat timeouts, and disconnect cleanup release held keys/buttons. Remote
administration is not exposed over HTTP. Windows identity secrets use user-scoped
DPAPI; phone signing keys are non-extractable IndexedDB keys.

A compromised hosting origin can replace its browser client; signed signaling
does not solve compromised client code. TURN credential limits reduce abuse but
are not a guaranteed spending cap. Read [SECURITY.md](SECURITY.md), the
[threat model](docs/REMOTE-THREAT-MODEL.md), and [deployment guide](cloud/README.md).

Ordinary desktop apps are supported. UAC, the Windows lock screen, secure attention
and elevated apps are outside scope. Do not run Deskpad as administrator to bypass
these boundaries. There is no file transfer or laptop clipboard-reading feature.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check host
npm test --prefix web
npm run build --prefix web
npm ci --prefix cloud
npm run check --prefix cloud
npm test --prefix cloud
```

On Linux/macOS, use `.venv/bin/python` and `deskpad-desktop --demo` for synthetic
UI work. Native capture/control is Windows-only. The browser tests include fake
camera/mic devices and a test-only signaling harness; they do not establish live
Cloudflare TURN, physical Safari, or Zoom acceptance.

See [architecture](docs/ARCHITECTURE.md), [protocol](docs/PROTOCOL.md),
[testing](docs/TESTING.md), and [contribution instructions](CONTRIBUTING.md).

Deskpad source is MIT licensed. Binary distributions include independently licensed
components; read [third-party notices](THIRD-PARTY-NOTICES.md) before redistributing.

Desktop update architecture and maintainer activation: [docs/UPDATES.md](docs/UPDATES.md). The signed alpha update channel is live. Install a current alpha once to get the updater. Windows CI verifies installation, updater handoff, restart, settings/pairing persistence and uninstall; physical Windows/iPhone/Zoom acceptance is still pending.
