"""Local pairing and expiring device credentials. Raw credentials are never persisted."""

import hashlib
import json
import os
import secrets
import tempfile
import time
from pathlib import Path


class Pairing:
    def __init__(self, path: Path, lifetime=30 * 86400):
        self.path, self.lifetime = path, lifetime
        self.pin = f"{secrets.randbelow(1000000):06d}"
        self.failures = {}
        self.devices = {}
        if path.exists():
            self.devices = json.loads(path.read_text(encoding="utf-8"))
        self._prune()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _prune(self):
        now = time.time()
        self.devices = {k: v for k, v in self.devices.items() if v > now}
        self.failures = {k: v for k, v in self.failures.items() if now - v[0] < 60}

    def pair(self, pin, client):
        self._prune()
        # Six guesses per minute per source, plus a global cap against unbounded attempts.
        for key, limit in ((client, 6), ("*", 30)):
            started, count = self.failures.get(key, (time.time(), 0))
            if count >= limit:
                raise ValueError("Too many attempts. Wait a minute.")
        if not secrets.compare_digest(pin, self.pin):
            for key in (client, "*"):
                started, count = self.failures.get(key, (time.time(), 0))
                self.failures[key] = (started, count + 1)
            raise ValueError("Incorrect pairing code.")
        if len(self.devices) >= 32:
            oldest = min(self.devices, key=self.devices.get)
            self.devices.pop(oldest)
        token = secrets.token_urlsafe(32)
        self.devices[self.digest(token)] = time.time() + self.lifetime
        self._save()
        return token

    def valid(self, token):
        return bool(token and self.devices.get(self.digest(token), 0) > time.time())

    def revoke(self, token):
        if token:
            self.devices.pop(self.digest(token), None)
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(self.devices, out)
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
