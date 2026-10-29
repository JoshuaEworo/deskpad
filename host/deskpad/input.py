"""Each controller owns its held keys and mouse buttons."""

from .protocol import Button, Key, Move, Release, Scroll, Shortcut, Text


class InputSession:
    def __init__(self, backend):
        self.backend = backend
        self.keys = set()
        self.buttons = set()

    def handle(self, message):
        b = self.backend
        match message:
            case Move(dx=dx, dy=dy):
                b.move(dx, dy)
            case Scroll(dx=dx, dy=dy):
                b.scroll(dx, dy)
            case Text(text=text):
                b.text(text)
            case Button(button=button, action=action):
                if action == "click":
                    # A click must not silently release an explicitly held drag.
                    if button not in self.buttons:
                        self._button(button, True)
                        self._button(button, False)
                else:
                    self._button(button, action == "down")
            case Key(key=key, action=action):
                if action == "press":
                    if key not in self.keys:
                        self._key(key, True)
                        self._key(key, False)
                else:
                    self._key(key, action == "down")
            case Shortcut(keys=keys):
                temporary = []
                try:
                    for key in keys:
                        if key not in self.keys:
                            self._key(key, True)
                            temporary.append(key)
                finally:
                    for key in reversed(temporary):
                        self._key(key, False)
            case Release():
                self.release()

    def _key(self, key, down):
        if down:
            self.keys.add(key)
        self.backend.key(key, down)
        if not down:
            self.keys.discard(key)

    def _button(self, button, down):
        if down:
            self.buttons.add(button)
        self.backend.button(button, down)
        if not down:
            self.buttons.discard(button)

    def release(self):
        if hasattr(self.backend, "motion"):
            self.backend.motion.clear()
        errors = []
        for key in list(self.keys):
            try:
                self._key(key, False)
            except Exception as exc:
                errors.append(exc)
        for button in list(self.buttons):
            try:
                self._button(button, False)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError("Could not release all remote inputs") from errors[0]
