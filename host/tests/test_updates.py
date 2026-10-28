import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from deskpad.updates import (
    REPOSITORY,
    check_update,
    download_update,
    verify_release,
    version_key,
)


def signed(**changes):
    key = Ed25519PrivateKey.generate()
    data = dict(
        version="0.2.0-alpha.6",
        platform="windows-x64",
        published=1000,
        expires=2000,
        notes="Release notes",
        size=5,
        url=f"https://github.com/{REPOSITORY}/releases/download/v0.2.0-alpha.6/Deskpad-Setup-Windows-x64.exe",
        sha256=hashlib.sha256(b"hello").hexdigest(),
    )
    data.update(changes)
    payload = json.dumps(data).encode()
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    envelope = dict(
        payload=base64.b64encode(payload).decode(),
        signature=base64.b64encode(key.sign(payload)).decode(),
    )
    return envelope, public


def test_signed_release_and_version_order():
    envelope, public = signed()
    assert verify_release(envelope, public, now=1100).version == "0.2.0-alpha.6"
    assert verify_release(envelope, public, current="0.2.0-alpha.6", now=1100) is None
    assert verify_release(envelope, public, current="0.2.0", now=1100) is None
    assert version_key("0.2.0-alpha.9") < version_key("0.2.0-alpha.10") < version_key("0.2.0")


def test_rejects_tampering_and_wrong_signer():
    envelope, public = signed()
    envelope["payload"] = base64.b64encode(
        base64.b64decode(envelope["payload"]).replace(b"notes", b"NOTES")
    ).decode()
    with pytest.raises(ValueError, match="signature"):
        verify_release(envelope, public, now=1100)
    envelope, _ = signed()
    with pytest.raises(ValueError, match="signature"):
        verify_release(envelope, public, now=1100)


@pytest.mark.parametrize(
    "changes",
    [
        {"expires": 1001},
        {"published": 2000},
        {"platform": "linux"},
        {"url": "http://github.com/malicious.exe"},
        {
            "url": "https://github.com/other/repo/releases/download/v0.2.0-alpha.6/Deskpad-Setup-Windows-x64.exe"
        },
        {"size": 500 * 1024 * 1024},
        {"sha256": "wrong"},
    ],
)
def test_rejects_expired_incompatible_or_untrusted_metadata(changes):
    envelope, public = signed(**changes)
    with pytest.raises(ValueError):
        verify_release(envelope, public, now=1100)


def test_download_is_hashed_and_progress_reported(tmp_path):
    envelope, public = signed()
    release = verify_release(envelope, public, now=1100)
    progress = []
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"hello"))
    )
    path = download_update(release, tmp_path, progress.append, client)
    assert path.read_bytes() == b"hello"
    assert progress[-1] == 100


@pytest.mark.parametrize("body", [b"bad", b"hello!", b"HELLO"])
def test_corrupt_truncated_or_oversized_download_is_removed(tmp_path, body):
    envelope, public = signed()
    release = verify_release(envelope, public, now=1100)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    with pytest.raises(ValueError):
        download_update(release, tmp_path, client=client)
    assert list(tmp_path.iterdir()) == []


def test_no_key_fails_closed_and_private_channel_is_explained():
    with pytest.raises(ValueError, match="not published"):
        check_update(public_key="")
    _, public = signed()
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404)))
    with pytest.raises(ValueError, match="No published"):
        check_update(public, client)
