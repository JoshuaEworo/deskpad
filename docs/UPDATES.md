# Desktop updates

The installed Windows app checks once per launch and then daily when automatic
checks are enabled. Settings → App updates also offers a manual check. Checks only
fetch public release metadata; they send no pairing keys, screen data or device ID.
Downloads and installation require explicit user actions. Installation is blocked
while a phone session is active. Portable/source builds can check but require the
Windows installer to enable in-place installation.

A signed Ed25519 envelope pins the release version, platform, HTTPS installer URL,
SHA-256, exact byte count, notes and validity window. The public key ships with the
app, separate from the configurable remote-service URL. Unconfigured keys, invalid
signatures, wrong repositories, expired metadata, downgrade attempts and corrupt
or oversized downloads fail closed. A checksum alone would not authenticate an
update: the manifest signature is required too.

The updater hands a verified installer to a detached Windows helper, then exits
normally to release remote input and stop the host. The helper waits for that
process, hashes the installer again, installs to the existing per-user app directory
without rebooting or force-closing other programs, and restarts Deskpad only on
successful exit. Settings and pairing state live outside the installation directory.
Failures leave a local install log and an error message. Inno Setup handles file
replacement; this is not a transactional A/B rollback system. Physical Windows
upgrade/failure-path acceptance remains a release gate.

## One-time maintainer activation

The repository is currently private and the pinned key is intentionally empty.
No update channel is live until the following setup is complete. Do not distribute
an initial updater build before pinning its public key; existing apps cannot safely
learn a new signing key from unsigned network configuration.

1. In the development environment run `python scripts/create_update_key.py PATH`
   with a private backup path **outside this repository**. This pins only the public
   key in `host/deskpad/update-key.json`; the private key file must never be committed.
2. Store the private file's base64 contents in the GitHub Actions environment
   `releases`, secret `DESKPAD_UPDATE_SIGNING_KEY`. Protect that environment and
   release tags so ordinary unreviewed code cannot sign a release. Back up the key
   offline. Do not send it in chat or add it to Cloudflare.
3. Commit the public key, make release downloads public, and distribute the first
   installer containing this updater and key. This is the final manual bootstrap.
4. Bump the matching versions in `updates.VERSION`, `pyproject.toml`, `uv.lock` and
   `scripts/installer.iss`; edit `RELEASE-NOTES.md`; push a matching `vVERSION` tag.
   Windows CI builds/tests the installer. The release job signs metadata and publishes
   the versioned assets before replacing the `update-channel` manifest.

Main-branch commits continue to build development artifacts but do not notify users
of an update. Only an explicitly published version tag updates the channel. This
alpha has one channel; opting in means receiving alpha releases too. Private source
can alternatively use a separate public release repository after changing the fixed
repository constant before the first signed build. No GitHub token is shipped to users.

Manifest signing is independent of Authenticode. It authenticates updates to existing
Deskpad installations; it does not remove Windows SmartScreen warnings for the first
installer. Code signing and signed virtual-device distribution remain separate work.

Key rotation requires a deliberate trust migration in an update signed by the old
key. Do not replace the pinned key and expect older clients to trust it automatically.
