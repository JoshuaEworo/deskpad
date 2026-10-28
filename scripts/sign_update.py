"""Release CI entry point; the signing key comes only from a protected Actions secret."""

import base64
import hashlib
import json
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from deskpad.updates import REPOSITORY, VERSION

root = Path(__file__).resolve().parents[1]
tag = os.environ["RELEASE_TAG"]
if tag != f"v{VERSION}":
    raise ValueError("Release tag must match the bundled desktop version")
key = Ed25519PrivateKey.from_private_bytes(
    base64.b64decode(os.environ["DESKPAD_UPDATE_SIGNING_KEY"], validate=True)
)
public = base64.b64encode(
    key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()
if public != json.loads((root / "host/deskpad/update-key.json").read_text())["public_key"]:
    raise ValueError("Release signing key does not match the app's pinned public key")
installer = root / "release/Deskpad-Setup-Windows-x64.exe"
now = int(time.time())
notes = (root / "RELEASE-NOTES.md").read_text(encoding="utf-8")
payload = json.dumps(
    dict(
        version=VERSION,
        platform="windows-x64",
        published=now,
        expires=now + 365 * 86400,
        url=f"https://github.com/{REPOSITORY}/releases/download/{tag}/{installer.name}",
        sha256=hashlib.sha256(installer.read_bytes()).hexdigest(),
        size=installer.stat().st_size,
        notes=notes,
    ),
    separators=(",", ":"),
).encode()
(root / "release/update.json").write_text(
    json.dumps(
        dict(
            payload=base64.b64encode(payload).decode(),
            signature=base64.b64encode(key.sign(payload)).decode(),
        )
    ),
    encoding="utf-8",
)
