"""Synthetic host for browser tests only; never use this fixed PIN for real sharing."""

import tempfile
from pathlib import Path

import uvicorn
from deskpad.server import create_app

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(
            state_path=Path(directory) / "devices.json",
            origins=["http://127.0.0.1:8766"],
            demo=True,
        )
        app.state.pairing.pin = "123456"

        @app.get("/test/events")
        async def events():
            return list(app.state.native.events)

        # Place this test-only route before the static catch-all.
        app.router.routes.insert(0, app.router.routes.pop())
        uvicorn.run(app, host="127.0.0.1", port=8766, access_log=False)
