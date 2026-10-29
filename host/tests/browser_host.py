"""Synthetic host for browser tests only; never use this fixed PIN for real sharing."""

import asyncio
import json
import secrets
import tempfile
from pathlib import Path

import uvicorn
from deskpad.identity import Identity
from deskpad.server import create_app
from deskpad.settings import Settings
from fastapi import Request, WebSocket, WebSocketDisconnect

if __name__ == "__main__":
    # CI network namespaces may expose only loopback; never patch this in production.
    try:
        import aioice.ice

        aioice.ice.get_host_addresses = lambda use_ipv4, use_ipv6: ["127.0.0.1"]
    except ImportError:
        pass
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(
            state_path=Path(directory) / "devices.json",
            origins=["http://127.0.0.1:8766"],
            demo=True,
            settings=Settings(),
            remote_identity=Identity(Path(directory)),
        )
        app.state.pairing.pin = "123456"
        app.state.test_remote_sockets = set()
        app.state.test_remote_offline = False

        @app.post("/test/reset")
        async def reset_test_events():
            await app.state.rtc.close()
            for _ in range(100):
                if app.state.lease["id"] is None:
                    break
                await asyncio.sleep(0.02)
            app.state.native.events.clear()
            app.state.native.x, app.state.native.y = 600, 350
            app.state.native.motion.clear()
            capture = app.state.rtc.capture

            def reset_displays():
                capture.demo_displays = [{"left": 0, "top": 0, "width": 1280, "height": 720}]
                capture._display_refresh = 0
                capture.monitor, capture.follow_cursor = 1, True
                capture._manual_until = 0

            await asyncio.get_running_loop().run_in_executor(app.state.rtc.executor, reset_displays)
            app.state.rtc.settings.camera = False
            app.state.rtc.settings.microphone = False
            app.state.rtc.settings.speakers = False
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/displays")
        async def two_displays():
            def update():
                capture = app.state.rtc.capture
                capture.demo_displays = [
                    {"left": 0, "top": 0, "width": 1280, "height": 720},
                    {"left": -1280, "top": 0, "width": 1280, "height": 720},
                ]
                capture._display_refresh = 0

            await asyncio.get_running_loop().run_in_executor(app.state.rtc.executor, update)
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/cursor")
        async def physical_cursor(request: Request):
            position = await request.json()
            app.state.native.x, app.state.native.y = position["x"], position["y"]
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.get("/test/events")
        async def events():
            return list(app.state.native.events)

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/media/allow")
        async def allow_media():
            from deskpad import media_devices

            app.state.media_events = []

            class TestSink:
                def __init__(self, kind, settings):
                    self.kind = kind
                    self.error = ""
                    app.state.media_events.append("opened:" + kind)

                def write(self, frame, enabled):
                    if enabled:
                        app.state.media_events.append(self.kind)

                def close(self):
                    app.state.media_events.append("closed:" + self.kind)

            media_devices.MediaSink = TestSink
            app.state.rtc.settings.camera = True
            app.state.rtc.settings.microphone = True
            app.state.rtc.settings.microphone_output = 0
            app.state.rtc.settings.microphone_output_name = "CABLE Input (VB-Audio Virtual Cable)"
            app.state.service.update(
                media_setup={
                    **{
                        name: {"ready": True, "state": "Ready", "detail": "Test device"}
                        for name in ("camera", "microphone", "speakers")
                    },
                    "outputs": [{"id": 0, "name": "CABLE Input (VB-Audio Virtual Cable)"}],
                }
            )
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.get("/test/media/events")
        async def media_events():
            return getattr(app.state, "media_events", [])

        app.router.routes.insert(0, app.router.routes.pop())

        @app.get("/test/remote")
        async def remote_config():
            remote = app.state.remote
            return {
                "v": 2,
                "room": remote.identity.room,
                "gate": remote.identity.gate,
                "host": remote.identity.public,
                "invite": remote.identity.invite,
                "name": "Test laptop",
            }

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/approve")
        async def approve_remote():
            remote = app.state.remote
            remote.settings.remote = True
            for identifier in list(remote.pending):
                await remote.approve(identifier)
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/remote-offline")
        async def remote_offline():
            app.state.test_remote_offline = True
            await app.state.rtc.close()
            app.state.remote.sessions.clear()
            app.state.remote.challenges.clear()
            for socket in list(app.state.test_remote_sockets):
                await socket.close(code=1012)
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/remote-online")
        async def remote_online():
            app.state.test_remote_offline = False
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.post("/test/revoke")
        async def revoke_remote():
            remote = app.state.remote
            for identifier in list(remote.identity.devices):
                await remote.revoke(identifier)
            return {"ok": True}

        app.router.routes.insert(0, app.router.routes.pop())

        @app.websocket("/api/rooms/{room}/socket")
        async def remote_socket(ws: WebSocket, room: str):
            remote = app.state.remote
            protocols = ws.headers.get("sec-websocket-protocol", "").split(", ")
            if room != remote.identity.room or "phone." + remote.identity.gate not in protocols:
                await ws.close(code=4403)
                return
            await ws.accept(subprotocol="deskpad")
            if app.state.test_remote_offline:
                await ws.close(code=1013)
                return
            app.state.test_remote_sockets.add(ws)
            target = secrets.token_urlsafe(16)

            async def send(recipient, body):
                if recipient == target:
                    await ws.send_json(remote.identity.sign(body))

            async def ice():
                return []

            remote.send = send
            remote.ice = ice
            try:
                while True:
                    packet = json.loads(await ws.receive_text())
                    await remote.handle(target, packet["message"])
            except WebSocketDisconnect:
                pass
            finally:
                app.state.test_remote_sockets.discard(ws)

        app.router.routes.insert(0, app.router.routes.pop())

        uvicorn.run(app, host="127.0.0.1", port=8766, access_log=False)
