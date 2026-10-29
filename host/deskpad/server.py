import asyncio
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import Pairing
from .capture import ScreenCapture
from .input import InputSession
from .media_setup import inspect_media
from .native import DemoInput, WindowsInput
from .protocol import INPUT_ADAPTER, Display, Ping
from .service import Service
from .settings import Settings

log = logging.getLogger("deskpad")
COOKIE = "deskpad_device"


class PairRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


def create_app(
    *,
    state_path: Path,
    origins: list[str],
    demo=False,
    monitor=1,
    fps=20,
    width=1440,
    quality=75,
    static_dir: Path | None = None,
    backend=None,
    service=None,
    settings=None,
    remote_identity=None,
):
    service = service or Service()
    settings = settings or Settings(monitor=monitor, fps=fps, width=width, quality=quality)
    sockets = set()
    pairing = Pairing(state_path)
    native = backend if backend is not None else (DemoInput() if demo else WindowsInput())
    capture = ScreenCapture(demo, monitor, width, quality)
    capture.cursor = native.position
    capture.follow_cursor = settings.follow_cursor
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deskpad-capture")
    input_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deskpad-input")
    setup_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deskpad-media-setup")
    lease = {"id": None, "token": None, "video": None}

    from .rtc import RtcHub

    rtc = RtcHub(native, capture, executor, input_executor, lease, service, settings)
    rtc.pairing = pairing
    remote = None
    if remote_identity is not None:
        from .remote import Remote

        remote = Remote(remote_identity, settings, service, rtc)
        remote.refresh()

    async def disconnect(reason=None):
        if reason:
            for peer in list(rtc.peers.values()):
                peer.send({"type": "session-ended", "reason": reason})
            await asyncio.gather(
                *(
                    ws.send_json({"type": "session-ended", "reason": reason})
                    for ws in list(sockets)
                ),
                return_exceptions=True,
            )
            # Let the reliable control channel flush before closing its transport.
            await asyncio.sleep(0.1)
        await rtc.close()
        await asyncio.gather(*(ws.close(code=1000) for ws in list(sockets)), return_exceptions=True)

    async def command(action, value):
        if action == "pause":
            service.update(paused=bool(value))
            if value:
                await disconnect()
        elif action == "disconnect":
            if remote:
                await remote.notify_sessions("ended")
            await disconnect("ended")
        elif action == "approve" and remote:
            await remote.approve(value)
        elif action == "reject" and remote:
            remote.pending.pop(value, None)
            remote.refresh()
        elif action == "revoke" and remote:
            await remote.revoke(value)
        elif action == "revoke-local":
            pairing.devices.pop(value, None)
            pairing._save()
            await disconnect("revoked")
        elif action == "new-invite":
            if remote and settings.remote:
                remote.new_invite()
            else:
                pairing.pin = f"{secrets.randbelow(1000000):06d}"
                service.update(pin=pairing.pin)
        elif action == "remote" and remote:
            settings.remote = bool(value)
            if value:
                await remote.start()
            else:
                await remote.stop()
        elif action == "settings":
            changes = Settings.model_validate(value)
            if any(
                getattr(settings, name) != getattr(changes, name)
                for name in (
                    "camera",
                    "microphone",
                    "speakers",
                    "microphone_output",
                    "microphone_output_name",
                    "speaker_input",
                )
            ):
                await disconnect()
            if changes.service_url != settings.service_url:
                if remote:
                    await remote.stop()
            if (
                changes.follow_cursor != settings.follow_cursor
                or changes.monitor != settings.monitor
            ):
                await asyncio.get_running_loop().run_in_executor(
                    executor, capture.configure_display, changes.monitor, changes.follow_cursor
                )
            for name, val in changes.model_dump().items():
                setattr(settings, name, val)
            capture.width, capture.quality = settings.width, settings.quality
            if remote and settings.remote:
                await remote.start()
            elif remote:
                await remote.stop()
        elif action == "refresh-media":
            await refresh_media()
        service.update(local_devices=list(pairing.devices))

    async def refresh_media():
        if service.snapshot()["media_scanning"]:
            return
        service.update(media_scanning=True)
        try:
            result = await asyncio.get_running_loop().run_in_executor(setup_executor, inspect_media)
            service.update(media_setup=result)
        finally:
            service.update(media_scanning=False)

    @asynccontextmanager
    async def lifespan(app):
        service.loop = asyncio.get_running_loop()
        service.handler = command
        service.update(running=True, pin=pairing.pin, local_devices=list(pairing.devices))
        probe = asyncio.create_task(refresh_media())
        if remote and settings.remote:
            await remote.start()
        try:
            yield
        finally:
            probe.cancel()
            await asyncio.gather(probe, return_exceptions=True)
            service.handler = None
            if remote:
                await remote.stop()
            await disconnect()
            service.update(running=False)

        await asyncio.get_running_loop().run_in_executor(executor, capture.close)
        executor.shutdown(wait=True)
        input_executor.shutdown(wait=True)
        setup_executor.shutdown(wait=True)

    app = FastAPI(
        title="Deskpad", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.pairing = pairing
    app.state.native = native
    app.state.lease = lease
    app.state.rtc = rtc
    app.state.service = service
    app.state.remote = remote
    hosts = [origin.split("://", 1)[1].split(":", 1)[0] for origin in origins]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(set(hosts)))

    def same_origin(connection):
        return connection.headers.get("origin") in origins

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/status")
    async def status(request: Request):
        return {
            "protocol": 1,
            "demo": demo,
            "paired": pairing.valid(request.cookies.get(COOKIE)),
            "busy": lease["id"] is not None,
            "rtc": __import__("importlib.util").util.find_spec("aiortc") is not None,
        }

    @app.post("/api/pair")
    async def pair(body: PairRequest, request: Request, response: Response):
        if not same_origin(request) or service.snapshot()["paused"]:
            raise HTTPException(403, "Open Deskpad directly from the host's address.")
        try:
            token = pairing.pair(body.code, request.client.host)
        except ValueError as exc:
            raise HTTPException(429, str(exc)) from exc
        response.set_cookie(
            COOKIE,
            token,
            max_age=pairing.lifetime,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )
        service.update(local_devices=list(pairing.devices))
        return {"paired": True}

    @app.post("/api/forget")
    async def forget(request: Request, response: Response):
        if not same_origin(request):
            raise HTTPException(403)
        token = request.cookies.get(COOKIE)
        pairing.revoke(token)
        service.update(local_devices=list(pairing.devices))
        if token and lease["token"] == token:
            await disconnect("revoked")
        response.delete_cookie(COOKIE)
        return {"paired": False}

    class Offer(BaseModel):
        sdp: str = Field(min_length=1, max_length=110000)

    @app.post("/api/rtc")
    async def offer(body: Offer, request: Request):
        if (
            not same_origin(request)
            or not pairing.valid(request.cookies.get(COOKIE))
            or service.snapshot()["paused"]
        ):
            raise HTTPException(403)
        try:
            answer = await rtc.offer("local:" + secrets.token_urlsafe(16), body.sdp, [])
            lease["token"] = request.cookies.get(COOKIE)
            return {"sdp": answer, "type": "answer"}
        except ImportError as exc:
            raise HTTPException(503, "WebRTC dependencies are not installed") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    async def authorized(ws):
        if (
            not same_origin(ws)
            or not pairing.valid(ws.cookies.get(COOKIE))
            or service.snapshot()["paused"]
        ):
            await ws.close(code=4403)
            return False
        return True

    @app.websocket("/ws/control")
    async def control(ws: WebSocket):
        if not await authorized(ws):
            return
        if lease["id"] is not None:
            await ws.close(code=4409)
            return
        connection_id = secrets.token_urlsafe(16)
        token = ws.cookies.get(COOKIE)
        lease.update(id=connection_id, token=token)
        session = InputSession(native)
        await ws.accept()
        sockets.add(ws)
        service.update(connected=True)
        try:
            await ws.send_json(
                {
                    "type": "hello",
                    "protocol": 1,
                    "connection": connection_id,
                    "demo": demo,
                    "cursor": native.position(),
                }
            )
            while pairing.valid(token) and not service.snapshot()["paused"]:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=8)
                if len(raw) > 16384:
                    await ws.close(code=1009)
                    break
                try:
                    message = INPUT_ADAPTER.validate_json(raw)
                except ValidationError:
                    await ws.send_json({"type": "error", "message": "Unsupported input message."})
                    continue
                if isinstance(message, Display):
                    try:
                        await rtc.configure_display(message)
                    except ValueError as error:
                        await ws.send_json({"type": "error", "message": str(error)})
                elif isinstance(message, Ping):
                    await ws.send_json({"type": "pong", "timestamp": message.timestamp})
                else:
                    await asyncio.get_running_loop().run_in_executor(
                        input_executor, session.handle, message
                    )
                    if message.type == "move":
                        await ws.send_json({"type": "cursor", "position": native.position()})
        except (WebSocketDisconnect, TimeoutError):
            pass
        except Exception:
            log.exception("Control session failed")
            try:
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "Windows input failed. Reconnect or check the host.",
                    }
                )
            except Exception:
                pass
        finally:
            sockets.discard(ws)
            service.update(connected=False)
            # The same worker serializes input and cleanup even if the ASGI task is cancelled.
            cleanup = asyncio.get_running_loop().run_in_executor(input_executor, session.release)

            def released(future):
                try:
                    future.result()
                except Exception:
                    log.exception("Input cleanup failed")
                finally:
                    if lease["id"] == connection_id:
                        lease.update(id=None, token=None)

            cleanup.add_done_callback(released)
            await asyncio.shield(cleanup)
            try:
                await ws.close()
            except (RuntimeError, WebSocketDisconnect):
                pass

    @app.websocket("/ws/video")
    async def video(ws: WebSocket):
        if not await authorized(ws):
            return
        connection_id = ws.query_params.get("connection")
        if (
            not connection_id
            or connection_id != lease["id"]
            or lease["video"] == connection_id
            or ws.cookies.get(COOKIE) != lease["token"]
        ):
            await ws.close(code=4409)
            return
        lease["video"] = connection_id
        await ws.accept()
        try:
            while lease["id"] == connection_id and pairing.valid(ws.cookies.get(COOKIE)):
                started = time.monotonic()
                meta, jpeg = await asyncio.get_running_loop().run_in_executor(
                    executor, capture.frame
                )
                meta["cursor"] = native.position()
                await ws.send_json(meta)
                await ws.send_bytes(jpeg)
                # Exactly one outstanding frame. A slow phone never accumulates old frames.
                ack = await asyncio.wait_for(ws.receive_text(), timeout=8)
                if ack != "ack":
                    await ws.close(code=1008)
                    break
                await asyncio.sleep(max(0, 1 / fps - (time.monotonic() - started)))
        except (WebSocketDisconnect, TimeoutError):
            pass
        except Exception:
            log.exception("Screen capture failed")
            try:
                await ws.send_json(
                    {
                        "type": "error",
                        "message": "Screen capture failed. Check the selected monitor on the host.",
                    }
                )
            except Exception:
                pass
        finally:
            if lease["video"] == connection_id:
                lease["video"] = None
            try:
                await ws.close()
            except (RuntimeError, WebSocketDisconnect):
                pass

    directory = static_dir or Path(__file__).with_name("static")
    if directory.exists():
        app.mount("/assets", StaticFiles(directory=directory / "assets"), name="assets")

        @app.get("/{path:path}")
        async def frontend(path: str):
            if path in ("", "index.html"):
                return FileResponse(directory / "index.html", headers={"Cache-Control": "no-cache"})
            if path in ("icon.svg", "manifest.webmanifest"):
                return FileResponse(directory / path)
            raise HTTPException(404)

    return app
