# Deskpad implementation plan

## First useful release

**Outcome:** a Windows user can start a host, pair an iPhone, and comfortably use existing desktop apps with the desktop visible above separate controls.

### 1. Foundation and executable vertical slice

- [x] Record scope, architecture, transport, and acceptance gates.
- [x] Windows capture/input boundary and synthetic demo mode.
- [x] Same-origin phone UI and host-served build.
- [x] QR address, six-digit pairing, remembered credentials, revocation.
- [x] Exclusive controller session and bounded video pipeline.
- [x] Distinguish real device validation from synthetic automated results.

### 2. Core ergonomics

- [x] Portrait screen/trackpad separation and resizable divider.
- [x] Viewer pinch, pan, and reset.
- [x] Relative trackpad, gestures, explicit mouse buttons, drag lock.
- [x] Native phone text field, desktop keys, modifiers, common shortcuts.
- [x] Text-send box for phone paste/dictation.
- [x] Preferences, connection status, reconnect, cleanup.
- [ ] Validate native keyboard, IME, dictation, and viewport on physical iPhone.
- [ ] Tune gesture thresholds and pointer speed through actual use.

### 3. Reliability and source distribution

- [x] Automated protocol/auth/lifecycle and gesture tests.
- [x] Browser integration test harness and screenshot capture.
- [x] Document reproducible setup and limitations.
- [x] CI and build-only Windows executable workflow.
- [ ] Complete Windows capture/input smoke tests with real apps.
- [ ] Verify executable on a clean Windows machine without Python/Node.
- [ ] Confirm Wi-Fi reconnect, laptop sleep/wake, and multi-monitor DPI behavior.

### 4. Public release gate

- [ ] Complete and record the matrix in TESTING.md.
- [ ] Profile 1440px / 20fps default on a typical home Wi-Fi connection.
- [ ] Fix material bugs found during daily use; no hidden prototype limitations.
- [ ] Test README from a fresh clone and downloaded build.
- [ ] Decide whether trusted-LAN plaintext scope is sufficient for first public alpha or HTTPS is required first.
- [ ] Add real screenshots and measured performance, then tag an alpha release.
- [ ] Repository visibility/publication is a separate owner action; this implementation does not change it.

## Later, driven by evidence

Hardware video encoding/WebRTC, desktop tray UI, audio, multi-monitor switching, clipboard sync, and secure internet access are deliberately later. Do not add these before the portrait workflow is useful on a real phone.
