"""Thread boundary between Qt and asyncio. The desktop is the only admin interface."""

import asyncio
import threading
from copy import deepcopy


class Service:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "running": False,
            "paused": False,
            "connected": False,
            "remote_status": "Local only",
            "pending": [],
            "devices": [],
            "error": "",
            "url": "",
            "pin": "",
        }
        self.loop = None
        self.handler = None

    def update(self, **values):
        with self._lock:
            self._state.update(values)

    def snapshot(self):
        with self._lock:
            return deepcopy(self._state)

    def command(self, action, value=None):
        if self.loop and self.handler:
            future = asyncio.run_coroutine_threadsafe(self.handler(action, value), self.loop)
            future.add_done_callback(self._completed)

    def _completed(self, future):
        try:
            future.result()
        except Exception as error:
            self.update(error=str(error))
