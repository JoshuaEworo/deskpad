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
        assert not calls and sent[-1]["code"] == "access-removed"
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
        assert sent[-1]["code"] == "access-removed"

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


def test_empty_saved_service_uses_bundled_origin_without_enabling_remote(tmp_path):
    path = tmp_path / "settings.json"
    Settings(name="My PC", remote=False).save(path)
    loaded = Settings.load(path)
    assert loaded.service_url == "https://deskpad.eworojoshua.workers.dev"
    assert not loaded.remote and loaded.name == "My PC"
    Settings(service_url="https://self-hosted.example", remote=True).save(path)
    assert Settings.load(path).service_url == "https://self-hosted.example"


def test_revocation_notifies_every_live_transport_and_rejects_reconnect(tmp_path):
    async def scenario():
        host, phone = Identity(tmp_path / "host"), Identity(tmp_path / "phone")
        identifier = key_id(phone.public)
        host.approve(identifier, phone.public, "Phone")
        closed = []

        class Peer:
            async def close(self):
                closed.append(True)

        class Hub:
            lease = {"id": None}
            peers = {"remote:" + identifier: Peer()}

            def paused(self):
                return False

        remote = Remote(host, Settings(remote=True), Service(), Hub())
        sent = []

        async def send(target, body):
            sent.append((target, body))

        remote.send = send
        remote.sessions = {
            "tab1": {"id": identifier, "nonce": "fresh-1"},
            "tab2": {"id": identifier, "nonce": "fresh-2"},
        }
        await remote.revoke(identifier)
        assert closed and not host.devices
        assert [body["nonce"] for _, body in sent] == ["fresh-1", "fresh-2"]
        assert all(body["reason"] == "revoked" for _, body in sent)
        await remote.handle("new-tab", envelope(phone, kind="connect"))
        assert sent[-1][1]["code"] == "access-removed"
        assert not remote.sessions

    asyncio.run(scenario())


def test_invite_rotation_keeps_pending_approval_valid(tmp_path, monkeypatch):
    async def scenario():
        host = Identity(tmp_path / "host")
        service = Service()
        remote = Remote(host, Settings(service_url="https://deskpad.example"), service, None)
        remote.new_invite()
        previous = host.invite
        remote.pending["phone"] = {"expires": time.time() + 120}
        host.invite_until = 0
        calls = 0

        async def tick(_):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise asyncio.CancelledError

        monkeypatch.setattr("deskpad.remote.asyncio.sleep", tick)
        with pytest.raises(asyncio.CancelledError):
            await remote.rotate_invites()
        assert host.invite != previous
        assert "phone" in remote.pending
        assert service.snapshot()["invite_until"] > time.time()

    asyncio.run(scenario())
