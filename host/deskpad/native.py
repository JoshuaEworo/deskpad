"""Platform boundary: native Windows SendInput, or a harmless demo adapter."""

import ctypes
import math
import sys
from collections import deque

KEYS = {
    "Control": 0x11,
    "Alt": 0x12,
    "Shift": 0x10,
    "Meta": 0x5B,
    "Enter": 0x0D,
    "Tab": 9,
    "Escape": 0x1B,
    "Backspace": 8,
    "Delete": 0x2E,
    "ArrowUp": 0x26,
    "ArrowDown": 0x28,
    "ArrowLeft": 0x25,
    "ArrowRight": 0x27,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    **{chr(i): ord(chr(i).upper()) for i in range(ord("a"), ord("z") + 1)},
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
}
EXTENDED = {
    "Meta",
    "Delete",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "PageUp",
    "PageDown",
}


class RelativeMotion:
    """Keep subpixel intent without issuing stationary Windows cursor writes."""

    def __init__(self):
        self.x = self.y = 0.0

    def take(self, dx, dy):
        self.x += dx
        self.y += dy
        x, y = math.trunc(self.x), math.trunc(self.y)
        self.x -= x
        self.y -= y
        return (x, y) if x or y else None

    def clear(self):
        self.x = self.y = 0.0


class DemoInput:
    def __init__(self):
        self.events = deque(maxlen=200)
        self.x, self.y = 600, 350
        self.motion = RelativeMotion()

    def position(self):
        return self.x, self.y

    def move(self, dx, dy):
        movement = self.motion.take(dx, dy)
        if not movement:
            return
        self.x += movement[0]
        self.y += movement[1]
        self.events.append(("move", dx, dy))

    def focus_display(self, bounds):
        self.motion.clear()
        self.x = bounds["left"] + bounds["width"] // 2
        self.y = bounds["top"] + bounds["height"] // 2

    def button(self, button, down):
        self.events.append(("button", button, down))

    def scroll(self, dx, dy):
        self.events.append(("scroll", dx, dy))

    def key(self, name, down):
        self.events.append(("key", name, down))

    def text(self, text):
        self.events.append(("text", text))


class WindowsInput:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Native input is Windows-only. Use --demo on other platforms.")
        from ctypes import wintypes as w

        # Fixed Windows widths; ULONG_PTR must follow the process pointer size.
        ptr = ctypes.c_size_t

        class Mouse(ctypes.Structure):
            _fields_ = [
                ("dx", w.LONG),
                ("dy", w.LONG),
                ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD),
                ("time", w.DWORD),
                ("dwExtraInfo", ptr),
            ]

        class Keyboard(ctypes.Structure):
            _fields_ = [
                ("wVk", w.WORD),
                ("wScan", w.WORD),
                ("dwFlags", w.DWORD),
                ("time", w.DWORD),
                ("dwExtraInfo", ptr),
            ]

        class Hardware(ctypes.Structure):
            _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]

        class Payload(ctypes.Union):
            _fields_ = [("mi", Mouse), ("ki", Keyboard), ("hi", Hardware)]

        class Input(ctypes.Structure):
            _anonymous_ = ("payload",)
            _fields_ = [("type", w.DWORD), ("payload", Payload)]

        self.Mouse, self.Keyboard, self.Input = Mouse, Keyboard, Input
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SendInput.argtypes = [w.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user.SendInput.restype = w.UINT
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
        self.user.GetCursorPos.restype = w.BOOL
        self.user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user.SetCursorPos.restype = w.BOOL
        self.Point = w.POINT
        self.motion = RelativeMotion()

    def _send(self, event):
        if self.user.SendInput(1, ctypes.byref(event), ctypes.sizeof(self.Input)) != 1:
            raise RuntimeError(
                "Windows refused input. Elevated apps and secure screens are unsupported."
            )

    def position(self):
        p = self.Point()
        if not self.user.GetCursorPos(ctypes.byref(p)):
            raise ctypes.WinError(ctypes.get_last_error())
        return p.x, p.y

    def move(self, dx, dy):
        movement = self.motion.take(dx, dy)
        if movement:
            x, y = self.position()
            if not self.user.SetCursorPos(x + movement[0], y + movement[1]):
                raise ctypes.WinError(ctypes.get_last_error())

    def focus_display(self, bounds):
        self.motion.clear()
        x, y = self.position()
        if not (
            bounds["left"] <= x < bounds["left"] + bounds["width"]
            and bounds["top"] <= y < bounds["top"] + bounds["height"]
        ):
            if not self.user.SetCursorPos(
                bounds["left"] + bounds["width"] // 2, bounds["top"] + bounds["height"] // 2
            ):
                raise ctypes.WinError(ctypes.get_last_error())

    def button(self, button, down):
        flag = {("left", True): 2, ("left", False): 4, ("right", True): 8, ("right", False): 16}[
            button, down
        ]
        self._send(self.Input(type=0, mi=self.Mouse(dwFlags=flag)))

    def scroll(self, dx, dy):
        for value, flag in ((-dy, 0x0800), (dx, 0x1000)):
            if value:
                self._send(
                    self.Input(
                        type=0,
                        mi=self.Mouse(mouseData=round(value * 120) & 0xFFFFFFFF, dwFlags=flag),
                    )
                )

    def key(self, name, down):
        flags = (0 if down else 2) | (1 if name in EXTENDED else 0)
        self._send(self.Input(type=1, ki=self.Keyboard(wVk=KEYS[name], dwFlags=flags)))

    def text(self, text):
        # Unicode packets avoid assumptions about the user's physical keyboard layout.
        for character in text.replace("\r\n", "\n").replace("\r", "\n"):
            if character in ("\n", "\t"):
                name = "Enter" if character == "\n" else "Tab"
                self.key(name, True)
                self.key(name, False)
                continue
            encoded = character.encode("utf-16-le")
            for i in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[i : i + 2], "little")
                for flags in (4, 6):
                    self._send(self.Input(type=1, ki=self.Keyboard(wScan=unit, dwFlags=flags)))


def enable_dpi_awareness():
    if sys.platform == "win32":
        # Must precede screen capture and cursor APIs, particularly with display scaling.
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
