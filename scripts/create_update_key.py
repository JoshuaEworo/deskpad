"""Maintainer-only, one-time key creation. Never commit the private output file."""

import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

parser = argparse.ArgumentParser()
parser.add_argument(
    "private_file", type=Path, help="Private key backup path OUTSIDE the repository"
)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
private_file = args.private_file.resolve()
if private_file.is_relative_to(root):
    raise ValueError("Store the signing key outside the repository")
public_file = root / "host/deskpad/update-key.json"
if json.loads(public_file.read_text()).get("public_key"):
    raise ValueError("A key is already pinned. Key rotation requires an intentional migration.")
key = Ed25519PrivateKey.generate()
private = base64.b64encode(
    key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
)
fd = os.open(private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as output:
    output.write(private)
public_file.write_text(
    json.dumps(
        {
            "public_key": base64.b64encode(
                key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ).decode()
        }
    )
    + "\n"
)
print(
    "Public key pinned. Add the PRIVATE file's contents as the GitHub Actions secret DESKPAD_UPDATE_SIGNING_KEY, then keep an offline backup. Do not send it in chat."
)
