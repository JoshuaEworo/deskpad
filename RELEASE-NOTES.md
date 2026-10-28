Deskpad 0.2.0-alpha.4

- Adds a public landing page with a Windows download and phone connection entry.
- Renders pairing QR modules on an exact pixel grid for reliable scanning.
- Adds QR scanning inside the phone site/PWA, with camera capture stopped on exit.
- Removes revoked phone access immediately and returns the phone to pairing.
- Makes End session explicit, retaining pairing and waiting for intentional reconnect.
- Recovers signaling after the desktop goes offline and comes back.
- Shows pairing and connection progress instead of a silent wait.
- Refreshes expired pairing QRs automatically, with a subtle countdown.
- Uses discovered ICE routes after four seconds when unused transports stall.
- Moves Pause sharing alongside status and removes repetitive desktop text.
- Bundles the raster Deskpad icon and explicitly assigns native Windows taskbar icons.
- Keeps the app open unless the update helper confirms it has started.

Camera and microphone still require supported installed virtual devices.
Windows native icon/build checks and upgrade acceptance run in CI; pinned shortcut
caches and physical iPhone/cellular/Zoom behavior require device acceptance.
