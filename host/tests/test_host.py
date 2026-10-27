import json
import time

import pytest
from deskpad.auth import Pairing
from deskpad.input import InputSession
from deskpad.native import DemoInput
from deskpad.protocol import INPUT_ADAPTER, Button, Key, Shortcut
from deskpad.server import create_app
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

ORIGIN = {"origin": "http://testserver"}


@pytest.fixture
def app(tmp_path):
    return create_app(
        state_path=tmp_path / "devices.json", origins=["http://testserver"], demo=True
    )


def pair(client, app):
    response = client.post("/api/pair", json={"code": app.state.pairing.pin}, headers=ORIGIN)
    assert response.status_code == 200
    return response


def test_pair_remember_expire_revoke(tmp_path):
    path = tmp_path / "devices.json"
    auth = Pairing(path)
    token = auth.pair(auth.pin, "phone")
    assert token not in path.read_text()
    assert Pairing(path).valid(token)
    auth.devices[auth.digest(token)] = time.time() - 1
    assert not auth.valid(token)
    token = auth.pair(auth.pin, "phone")
    auth.revoke(token)
    assert not Pairing(path).valid(token)


def test_pairing_rate_limit(tmp_path):
    auth = Pairing(tmp_path / "devices.json")
    wrong = "000000" if auth.pin != "000000" else "999999"
    for _ in range(6):
        with pytest.raises(ValueError, match="Incorrect"):
            auth.pair(wrong, "phone")
    with pytest.raises(ValueError, match="Too many"):
        auth.pair(auth.pin, "phone")


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "move", "dx": float("nan"), "dy": 0},
        {"type": "move", "dx": 999999, "dy": 0},
        {"type": "key", "key": "arbitrary", "action": "down"},
        {"type": "text", "text": "x" * 4097},
        {"type": "shortcut", "keys": []},
        {"type": "release", "execute": "anything"},
    ],
)
def test_protocol_rejects_invalid_input(payload):
    with pytest.raises(ValidationError):
        INPUT_ADAPTER.validate_python(payload)


def test_shortcut_preserves_existing_modifier_and_release():
    native = DemoInput()
    session = InputSession(native)
    session.handle(Key(type="key", key="Control", action="down"))
    session.handle(Shortcut(type="shortcut", keys=["Control", "c"]))
    assert session.keys == {"Control"}
    assert list(native.events) == [
        ("key", "Control", True),
        ("key", "c", True),
        ("key", "c", False),
    ]
    session.handle(Button(type="button", button="left", action="down"))
    session.release()
    assert not session.keys and not session.buttons
    assert ("button", "left", False) in native.events


def test_http_and_websocket_authorization(app):
    with TestClient(app) as client:
        assert not client.get("/api/status").json()["paired"]
        assert client.post("/api/pair", json={"code": app.state.pairing.pin}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/control", headers=ORIGIN):
                pass
        response = pair(client, app)
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/status").json()["paired"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/control", headers={"origin": "http://evil.example"}):
                pass
        assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 400
        assert client.post("/api/forget", headers=ORIGIN).status_code == 200
        assert not client.get("/api/status").json()["paired"]


def test_control_video_and_disconnect_cleanup(app):
    with TestClient(app) as client:
        pair(client, app)
        with client.websocket_connect("/ws/control", headers=ORIGIN) as control:
            hello = control.receive_json()
            assert hello["protocol"] == 1
            control.send_json({"type": "key", "key": "Control", "action": "down"})
            control.send_json({"type": "button", "button": "left", "action": "down"})
            control.send_json({"type": "ping", "timestamp": 123})
            assert control.receive_json() == {"type": "pong", "timestamp": 123}
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/control", headers=ORIGIN):
                    pass
            with client.websocket_connect(
                f"/ws/video?connection={hello['connection']}", headers=ORIGIN
            ) as video:
                metadata = video.receive_json()
                assert metadata["bounds"]["width"] == 1280
                assert video.receive_bytes().startswith(b"\xff\xd8")
                video.send_text("ack")
                assert video.receive_json()["sequence"] > metadata["sequence"]
                video.receive_bytes()
        deadline = time.monotonic() + 2
        while client.get("/api/status").json()["busy"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.get("/api/status").json()["busy"] is False
        assert ("key", "Control", False) in app.state.native.events
        assert ("button", "left", False) in app.state.native.events


def test_invalid_message_does_not_execute(app):
    with TestClient(app) as client:
        pair(client, app)
        with client.websocket_connect("/ws/control", headers=ORIGIN) as control:
            control.receive_json()
            control.send_text(json.dumps({"type": "key", "key": "unrecognized"}))
            assert control.receive_json()["type"] == "error"
            assert not app.state.native.events
