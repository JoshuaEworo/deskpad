# Contributing

Deskpad's first priority is a comfortable portrait iPhone controller for Windows. Start with the architecture, implementation plan, and device test checklist under `docs/`.

- Keep capture, native input, protocol, gesture recognition, and UI responsibilities separate.
- Add regression coverage for input ordering, held-key cleanup, gesture state, and protocol changes.
- Validate browser changes in Chromium and WebKit; describe physical iPhone checks separately.
- Keep frames/input bounded. Do not introduce queues that replay stale actions.
- Do not log user screens, typed content, pairing secrets, or device credentials.
- Record actual device/OS versions and measurements; do not substitute demo results for native validation.
- Avoid introducing services or dependencies without a concrete user benefit.

Run host tests/lint, client tests/build, and the relevant browser tests before a PR. Describe observable behavior and validation, not only files changed. No generated frontend build output, dependency folders, or local credentials in commits.

## Windows executable

The `Windows build` workflow runs on main and can also be started manually. It produces an unsigned zipped PyInstaller directory as a workflow artifact. It is a test build, not a published release. Download, extract the whole directory, and run `Deskpad.exe`. Verify it on a clean Windows machine before creating a public release. Windows signing/SmartScreen reputation is not configured.
