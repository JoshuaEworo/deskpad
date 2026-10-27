# Deskpad

**Your desktop above. Your controls below.**

A free, local-first remote desktop for a Windows laptop and an iPhone. Hold your phone upright: your existing desktop stays at the top, a dedicated trackpad sits underneath, and the phone keyboard opens at the bottom.

**Early alpha, not a verified Windows/iPhone release.** The host protocol and browser UI have automated tests. Real Windows screen capture/input and the physical iPhone keyboard still require the acceptance checks in [docs/TESTING.md](docs/TESTING.md). Demo mode is a synthetic screen and never controls your computer.

## What is here

- Edge-to-edge desktop fitted to width, with pinch zoom/pan preserved when the keyboard opens.
- Slim, resizable trackpad with tap, two-finger right click, scrolling, long-press drag, and double-tap drag. Pointer speed defaults to 4×, adjustable from 2.5× to 7×.
- Landscape desktop as a relative trackpad, with explicit Mouse/View modes and a docked, collapsible hotkey bar.
- Optional one-thumb scroll wheel, mouse buttons, and drag lock; tiny Deskpad branding and a menu float over the desktop.
- Native phone text input, desktop keys, one-shot modifiers, shortcuts, and a text-send box for pasting or dictation.
- QR address and six-digit pairing; remembered phone credentials expire after 30 days.
- One controller at a time; reconnect without replaying old input; held-input cleanup.
- Separate control/video connections and one outstanding JPEG frame to avoid video backlog.
- No account, subscription, telemetry, or third-party frontend requests.

## Run from source

Requirements: **Windows 10/11, Python 3.11+, Node.js 20.19+ or 22.12+**, and phone/laptop on the same trusted Wi-Fi network. Keep the laptop awake and its display active. Windows Home is supported; RDP is not used.

From PowerShell in the repository:

```powershell
.\scripts\start.ps1
```

The script installs the Python dependencies into `.venv`, installs/builds the phone client, and starts the host. It does not change your execution policy. If scripts are blocked, use the manual commands below or enable scripts according to your own Windows configuration.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -c requirements.lock
cd web
npm ci
npm run build
cd ..
.\.venv\Scripts\deskpad.exe
```

1. If Windows Firewall asks, allow the host on your **private** home network.
2. Scan the QR code from your phone, or type the printed URL in Safari.
3. Enter the pairing code printed in the host window.
4. Optionally use Safari **Share → Add to Home Screen**. Keep the host window open.

Pairing transfers focus to the phone keyboard during your Connect tap. When reopening an already-paired page, tap the small keyboard button once; Safari may require that user gesture to show the native keyboard. Tap it again to dismiss. The screen keeps its width/zoom while the keyboard opens. The divider adjusts trackpad height; mouse buttons, shortcuts, Fit width, drag lock, and connection details are under the floating `···` menu.

No QR discovery across networks: scanning opens the laptop's LAN address. If automatic address selection is wrong (VPN or multiple adapters), pass the laptop's Wi-Fi IPv4 address:

```powershell
.\.venv\Scripts\deskpad.exe --advertise 192.168.1.25
```

Host options:

```text
--port 8765        Listen port
--monitor 1        Capture one display (MSS index, starting at 1)
--fps 20           Frame rate cap: 5–30
--width 1440       Maximum encoded width: 960 / 1280 / 1440 / 1920
--quality 75       JPEG quality: 40–90
--bind 0.0.0.0     Listen on IPv4 interfaces
--forget-devices   Revoke all remembered phones and exit
--demo             Synthetic desktop; no screen capture or native input
```

## Controls

| Action | Gesture or button |
| --- | --- |
| Move pointer | One finger on trackpad |
| Left click | Tap, or left mouse button |
| Right click | Two-finger tap, or right mouse button |
| Scroll | Two fingers, or enable the side scroll wheel in the menu and drag it with one finger; reverse direction in settings |
| Drag | Hold still briefly, then move; double-tap and drag also works |
| Persistent drag | Menu → Drag lock; opening the menu releases held input |
| Zoom desktop | Portrait: pinch the screen. Landscape: select View, then pinch around the part you want to enlarge |
| Pan desktop | Portrait: drag the screen while zoomed. Landscape: select View, then drag |
| Type | Keyboard stays focused while using the trackpad/desktop keys; bottom-right button shows/hides it |
| Shortcut | Select Ctrl/Alt/Shift/Win, then a letter or desktop key; modifiers release afterward |
| Paste phone text | Menu → Send text; paste or dictate, then send |
| Paste laptop clipboard | Menu → Paste on PC |

Portrait keeps a separate trackpad beneath the screen. Landscape hides that trackpad and fits the entire desktop above a docked control bar; the bar never overlays the image. In **Mouse** mode, sliding over the desktop moves the real Windows cursor, and tapping clicks at the cursor position (not at the finger position). Two-finger tap right-clicks, two fingers scroll, and hold/double-tap drag works as on the portrait pad. In **View** mode, screen gestures only pan/zoom the viewer and send no mouse input. Switching modes releases held inputs.

The landscape bar collapses to a shorter rail with small branding, Mouse/View controls, a keyboard button, and an expand button. Collapse state is remembered. Landscape starts with the keyboard tucked away; open it explicitly when needed. Rotating back restores the portrait view and trackpad preferences, and attempts to restore keyboard focus if it was previously open. Safari may require a keyboard tap after rotation. Each orientation keeps its own in-session zoom/pan state.

## Limits worth knowing

- **Trusted LAN only.** The initial transport is HTTP/WebSocket, so network traffic is not encrypted. Do not port-forward it or use it on public Wi-Fi. Pairing prevents unauthenticated control; it does not encrypt the stream. See [SECURITY.md](SECURITY.md).
- Ordinary desktop apps only. Windows UAC prompts, the lock screen, secure attention/Ctrl+Alt+Delete, and apps running at a higher integrity level are unsupported. Do not run the host as administrator as a workaround.
- Streaming starts at 20 fps using JPEG, not hardware video encoding. No latency or FPS claim is made before device measurements. Text quality, bandwidth, and latency trade off against width/quality settings.
- One captured monitor and one controller. The host tracks the real cursor and overlays a pointer on the phone; it does not stream native cursor shapes.
- Phone text is committed text, not a full physical keyboard emulator. IME composition is sent on commit. Autocorrect is disabled; use Send text for reliable long pastes/dictation. Physical keyboard modifiers on the phone are not yet forwarded.
- No automatic cursor-follow zoom, audio, file transfer, clipboard reading, host tray app, unattended startup, or internet access in this version.
- Home Screen is a shortcut/standalone experience where supported. There is no offline service worker; normal LAN HTTP does not get all secure-context browser capabilities.

## Develop

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check host
cd web
npm test
npm run build
```

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/deskpad --demo`. Native remote control is Windows-only. `npm run dev` rebuilds the client when files change; serve it from the host and reload Safari. This keeps frontend and host on the same origin.

See [architecture](docs/ARCHITECTURE.md), [implementation plan](docs/PLAN.md), [wire protocol](docs/PROTOCOL.md), and [device testing](docs/TESTING.md). Contribution instructions are in [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed. Built for a useful, small first release, with replaceable capture and transport boundaries.
