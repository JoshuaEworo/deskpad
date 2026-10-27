# Validation and device acceptance

Automated checks are necessary but not sufficient for a remote input tool. A synthetic desktop does not validate Windows capture, SendInput delivery, Safari's native keyboard, or actual Wi-Fi latency.

## Initial implementation results

| Check | Result in development environment |
| --- | --- |
| Host protocol, pairing, lifecycle | 12 passed |
| Windows ABI / Unicode packet tests | 2 skipped on Linux; configured in Windows CI |
| Trackpad gesture tests | 5 passed |
| Production TypeScript/client build | Passed |
| Chromium integration with mobile viewport | 3 passed: keyboard-first layout/text, optional controls/drag ownership, real multi-touch right click and zoom preservation |
| Desktop WebKit integration | Not run successfully locally: required browser system libraries unavailable; configured in CI |
| Physical Windows + iPhone | Pending |

No Windows executable or physical-device performance result is claimed by these checks.

## Automated commands

```text
.venv/bin/python -m pytest
.venv/bin/python -m ruff check host
cd web
npm ci
npm test
npm run build
npx playwright install --with-deps chromium webkit
npm run test:e2e
```

On Windows replace the Python executable path with `.venv\Scripts\python.exe`. Browser tests spawn a temporary synthetic host with a fixed test PIN on loopback only. They never inject real input. The test PIN must never be used in production.

Unit tests cover authentication/expiry/revocation, attempt limits, invalid protocol rejection, modifier ownership, exclusive control, video framing, disconnect cleanup, and gesture transitions. Browser tests cover pairing, live JPEG decode, direct typing, modifier reset, reconnect, forgetting, full-width desktop sizing at visible viewport heights of 844/530/420/320px, and keyboard focus retention. Chromium CDP supplies real multi-touch events to verify two-finger right click and pinch zoom preservation; that multi-touch case is skipped in WebKit. Viewport-height simulation is not an actual onscreen iOS keyboard. Desktop WebKit with mobile emulation is not physical iOS.

## Required physical matrix (pending)

| Environment | Status |
| --- | --- |
| Windows 11 normal desktop, single display | Pending |
| Windows 10 normal desktop | Pending |
| Windows scaling at 100%, 150%, 200% | Pending |
| Multiple monitors, including negative coordinates/mixed DPI | Pending |
| iPhone Safari, current iOS | Pending |
| iPhone Home Screen standalone | Pending |
| Clean Windows machine running packaged executable | Pending |

## User acceptance script

1. Fresh clone/install: start host; QR address works; enter PIN; wrong PIN is clear; remembered phone reconnects after host restart. Forget phone and confirm re-pairing is required.
2. Confirm screen content matches the selected Windows monitor and the pointer tracks both phone movement and physical mouse movement. Change Windows display scaling and verify coordinates.
3. Open an ordinary editor. Type letters, punctuation, emoji, accents, Japanese/Chinese composition, repeated backspace, and multiline text. No doubled, missing, or reordered characters. Test phone dictation in Send text.
4. Pair and check whether the keyboard opens without another tap. Reopen the paired page and use the small keyboard button once. Open/close keyboard repeatedly. Screen remains visible, trackpad remains usable, no page jump, no accidental browser zoom, and keyboard dismissal restores space. Rotate and return to portrait.
5. Move cursor, single/double/right click, two-finger scroll, long-press drag, double-tap drag, mouse-button drag, drag lock. Select text in an editor and move a Windows window.
6. Ctrl+C/V/A/Z/Y, Alt+Tab, Shift+arrows, Windows key, Tab, Enter, Escape, Delete, PageUp/Down. Confirm modifiers release after the action.
7. Hold Ctrl or drag, then lock phone, switch apps, close tab, disconnect Wi-Fi, or stop host. Inputs must release after disconnect/timeout. Reconnect must not replay actions.
8. Open another tab/phone while controlling. It must report busy without moving the mouse. Close original; second controller can connect.
9. Zoom/pan/reset screen and adjust divider with keyboard visible. Screen gestures must never send Windows input.
10. Run for 30 minutes on home Wi-Fi. Watch CPU/memory/bandwidth, text readability, input RTT, capture errors, and phone heat. Move farther from router and verify slowdown does not accumulate old frames.
11. Sleep/wake laptop: UI reconnects when desktop is available. Lock/UAC/elevated app behavior must match documented limitations, not imply supported control.

Record OS versions, display dimensions/scaling, host settings, and observed issues in a GitHub issue. Do not attach pairing codes, device credentials, personal desktop screenshots, or sensitive typed text.
