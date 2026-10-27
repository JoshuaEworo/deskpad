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
from .native import DemoInput, WindowsInput
from .protocol import INPUT_ADAPTER, Ping

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
):
    pairing = Pairing(state_path)
    native = backend if backend is not None else (DemoInput() if demo else WindowsInput())
    capture = ScreenCapture(demo, monitor, width, quality)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deskpad-capture")
    input_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deskpad-input")
    lease = {"id": None, "token": None, "video": None}

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.get_running_loop().run_in_executor(executor, capture.close)
        executor.shutdown(wait=True)
        input_executor.shutdown(wait=True)

    app = FastAPI(
        title="Deskpad", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.pairing = pairing
    app.state.native = native
    app.state.lease = lease
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
            "img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; "
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
        }

    @app.post("/api/pair")
    async def pair(body: PairRequest, request: Request, response: Response):
        if not same_origin(request):
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
        return {"paired": True}

    @app.post("/api/forget")
    async def forget(request: Request, response: Response):
        if not same_origin(request):
            raise HTTPException(403)
        pairing.revoke(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE)
        return {"paired": False}

    async def authorized(ws):
        if not same_origin(ws) or not pairing.valid(ws.cookies.get(COOKIE)):
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
            while pairing.valid(token):
                raw = await asyncio.wait_for(ws.receive_text(), timeout=8)
                if len(raw) > 16384:
                    await ws.close(code=1009)
                    break
                try:
                    message = INPUT_ADAPTER.validate_json(raw)
                except ValidationError:
                    await ws.send_json({"type": "error", "message": "Unsupported input message."})
                    continue
                if isinstance(message, Ping):
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
