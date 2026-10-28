import asyncio
import secrets
import time

import pytest
from cryptography.exceptions import InvalidSignature
from deskpad.identity import Identity, key_id, verify
from deskpad.remote import Remote
from deskpad.service import Service
from deskpad.settings import Settings


def envelope(identity, **values):
    return {
        **identity.sign({"time": time.time(), "nonce": secrets.token_urlsafe(24), **values}),
        "key": identity.public,
    }


def test_identity_persistence_signature_and_replay(tmp_path):
    host = Identity(tmp_path / "host")
    phone = Identity(tmp_path / "phone")
    message = envelope(phone, kind="connect")
    identifier, public, value = host.check(message)
    assert identifier == key_id(phone.public)
    assert value["kind"] == "connect"
    with pytest.raises(ValueError, match="Repeated"):
        host.check(message)
    host.approve(identifier, public, "My phone")
    assert Identity(tmp_path / "host").devices[identifier]["name"] == "My phone"
    assert Identity(tmp_path / "host").public == host.public
    assert host.owner not in host.path.read_text()
    assert host.gate not in host.path.read_text()
    host.revoke(identifier)
    assert not Identity(tmp_path / "host").devices
    tampered = {**message, "payload": message["payload"].replace("connect", "execute")}
    with pytest.raises(InvalidSignature):
        verify(tampered, phone.public)
    with pytest.raises(ValueError, match="clock"):
        host.check(envelope(phone, kind="connect", time=0))
    with pytest.raises(ValueError, match="clock"):
        host.check(envelope(phone, kind="connect", time=float("nan")))


def test_remote_requires_approval_challenge_and_rejects_replay(tmp_path):
    async def scenario():
        host = Identity(tmp_path / "host")
        phone = Identity(tmp_path / "phone")
        calls = []

        class Hub:
            lease = {"id": None}
            peers = {}

            def paused(self):
                return False

            async def offer(self, owner, sdp, ice):
                calls.append((owner, sdp))
                return "signed-answer"

        service = Service()
        remote = Remote(
            host, Settings(remote=True, service_url="https://deskpad.example"), service, Hub()
        )
        sent = []

        async def send(target, body):
            sent.append(body)

        async def ice():
            return []

        remote.send = send
        remote.ice = ice
        await remote.handle("phone", envelope(phone, kind="connect"))
        assert not calls and "Approve" in sent[-1]["message"]
        await remote.handle("phone", envelope(phone, kind="pair", invite="bad"))
        assert not service.snapshot()["pending"]
        await remote.handle("phone", envelope(phone, kind="pair", invite=host.invite, name="Phone"))
        assert service.snapshot()["pending"][0]["code"] == host.pairing_code(phone.public)
        await remote.approve(key_id(phone.public))
        await remote.handle("phone", envelope(phone, kind="offer", challenge="wrong", sdp="offer"))
        assert not calls
        await remote.handle("phone", envelope(phone, kind="connect"))
        challenge = sent[-1]["challenge"]
        offer = envelope(phone, kind="offer", challenge=challenge, sdp="offer")
        await remote.handle("different-transport", offer)
        assert not calls
        await remote.handle("phone", envelope(phone, kind="connect"))
        challenge = sent[-1]["challenge"]
        offer = envelope(phone, kind="offer", challenge=challenge, sdp="offer")
        await remote.handle("phone", offer)
        assert len(calls) == 1 and sent[-1]["sdp"] == "signed-answer"
        await remote.handle("phone", offer)
        assert len(calls) == 1
        await remote.revoke(key_id(phone.public))
        await remote.handle("phone", envelope(phone, kind="connect"))
        assert "Approve" in sent[-1]["message"]

    asyncio.run(scenario())


def test_settings_only_accept_https_origins():
    for url in ("http://example.com", "https://user:pass@example.com", "https://example.com/path"):
        with pytest.raises(ValueError):
            Settings(service_url=url)
    assert Settings(service_url="https://deskpad.example/").service_url == "https://deskpad.example"


def test_speaker_capture_requires_phone_opt_in(monkeypatch):
    np = pytest.importorskip("numpy")
    from deskpad.media_devices import SystemAudio

    source = SystemAudio(Settings(speakers=True))
    # With laptop permission enabled, phone opt-out must still produce silence
    # without touching the platform audio API.
    import builtins

    original = builtins.__import__

    def checked_import(name, *args, **kwargs):
        if name == "soundcard":
            raise AssertionError("Audio captured without phone opt-in")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked_import)
    assert np.count_nonzero(source.read(False)) == 0
