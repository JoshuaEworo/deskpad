"""Typed configuration and atomic persistence. No settings endpoint is exposed to phones."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


def state_directory():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "Deskpad"


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    name: str = Field(default="My laptop", min_length=1, max_length=64)
    remote: bool = False
    # A release may supply a hosted URL. No pretend live service is hard-coded.
    service_url: str = ""
    monitor: int = Field(default=1, ge=1, le=32)
    follow_cursor: bool = True
    fps: int = Field(default=30, ge=5, le=60)
    width: int = Field(default=1440, ge=640, le=3840)
    quality: int = Field(default=75, ge=40, le=90)
    port: int = Field(default=8765, ge=1024, le=65535)
    check_updates: bool = True
    keep_awake: bool = True
    launch_at_login: bool = False
    camera: bool = False
    microphone: bool = False
    speakers: bool = False
    microphone_output: int | None = None
    microphone_output_name: str = ""
    speaker_input: str = ""

    @field_validator("service_url")
    @classmethod
    def secure_service(cls, value):
        value = value.rstrip("/")
        if not value:
            return value
        url = urlparse(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("Use an HTTPS service origin without a path or credentials.")
        return value

    @classmethod
    def load(cls, path):
        settings = cls.model_validate_json(path.read_text()) if path.exists() else cls()
        if settings.service_url:
            return settings
        deployment = Path(__file__).with_name("deployment.json")
        origin = (
            json.loads(deployment.read_text()).get("service_url", "") if deployment.exists() else ""
        )
        settings.service_url = origin
        return settings

    def save(self, path):
        atomic_json(path, self.model_dump())
