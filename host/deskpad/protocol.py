"""Versioned, bounded input messages. Never accept arbitrary native key codes."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

KeyName = Literal[
    "Control",
    "Alt",
    "Shift",
    "Meta",
    "Enter",
    "Tab",
    "Escape",
    "Backspace",
    "Delete",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Move(Message):
    type: Literal["move"]
    dx: float = Field(ge=-2000, le=2000)
    dy: float = Field(ge=-2000, le=2000)


class Button(Message):
    type: Literal["button"]
    button: Literal["left", "right"]
    action: Literal["down", "up", "click"]


class Scroll(Message):
    type: Literal["scroll"]
    dx: float = Field(default=0, ge=-100, le=100)
    dy: float = Field(ge=-100, le=100)


class Text(Message):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=4096)


class Key(Message):
    type: Literal["key"]
    key: KeyName
    action: Literal["down", "up", "press"] = "press"


class Shortcut(Message):
    type: Literal["shortcut"]
    keys: list[KeyName] = Field(min_length=1, max_length=5)


class Release(Message):
    type: Literal["release"]


class MediaState(Message):
    type: Literal["media"]
    kind: Literal["camera", "microphone"]
    enabled: bool = Field(strict=True)


class Ping(Message):
    type: Literal["ping"]
    timestamp: float


Input = Annotated[
    Move | Button | Scroll | Text | Key | Shortcut | Release | Ping | MediaState,
    Field(discriminator="type"),
]
INPUT_ADAPTER = TypeAdapter(Input)
