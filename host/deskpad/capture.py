"""Capture and encoding stay on one worker thread; no queued historical frames."""

import io
import logging
import os
import time

from PIL import Image, ImageDraw


class ScreenCapture:
    def __init__(self, demo=False, monitor=1, width=1440, quality=75):
        self.demo, self.monitor = demo, monitor
        self.width, self.quality = width, quality
        self._mss = None
        self._gpu = None
        self._gpu_failed = False
        self.sequence = 0
        self.follow_cursor = True
        self.cursor = lambda: (0, 0)
        self._display_refresh = 0.0
        self._manual_until = 0.0
        self.view_info = {}
        self._displays = []

    def displays(self):
        # All MSS lifetime/enumeration stays on the capture worker. Reopen
        # periodically to detect hotplug instead of using MSS's cached topology.
        now = time.monotonic()
        if not self._displays or now - self._display_refresh >= 2:
            if self.demo:
                monitors = getattr(
                    self, "demo_displays", [{"left": 0, "top": 0, "width": 1280, "height": 720}]
                )
            else:
                if self._mss is not None:
                    self._mss.close()
                import mss

                self._mss = mss.mss()
                monitors = [dict(item) for item in self._mss.monitors[1:33]]
            self._displays = [
                {"id": i + 1, "name": f"Display {i + 1}", **b} for i, b in enumerate(monitors)
            ]
            self._display_refresh = now
        if not self._displays:
            raise RuntimeError("No displays are available")
        return self._displays

    def configure_display(self, monitor=None, follow_cursor=None):
        displays = self.displays()
        selected = next((item for item in displays if item["id"] == monitor), None)
        if monitor is not None and selected is None:
            raise ValueError("That display is no longer connected")
        if follow_cursor is not None:
            self.follow_cursor = follow_cursor
        if selected:
            self.monitor = monitor
            self._manual_until = time.monotonic() + 0.5
        return selected

    def active_display(self):
        displays = self.displays()
        if self.follow_cursor and time.monotonic() >= self._manual_until:
            x, y = self.cursor()
            containing = next(
                (
                    d
                    for d in displays
                    if d["left"] <= x < d["left"] + d["width"]
                    and d["top"] <= y < d["top"] + d["height"]
                ),
                None,
            )
            if containing:
                self.monitor = containing["id"]
        selected = next((d for d in displays if d["id"] == self.monitor), displays[0])
        self.monitor = selected["id"]
        self.view_info = {
            "displays": displays,
            "monitor": self.monitor,
            "followCursor": self.follow_cursor,
        }
        return {key: selected[key] for key in ("left", "top", "width", "height")}

    def image(self):
        bounds = self.active_display()
        if self.demo:
            image = Image.new("RGB", (1280, 720), "#141c26")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((65, 55, 1215, 665), radius=20, fill="#202d3c")
            draw.text((100, 95), "DESKPAD / DEMO DESKTOP", fill="#a8eacb", font_size=28)
            draw.text(
                (100, 180), "Your desktop above. Your controls below.", fill="white", font_size=36
            )
            draw.text(
                (100, 255),
                "Demo mode tests the interface without controlling this computer.",
                fill="#b7c5d6",
                font_size=23,
            )
            draw.text(
                (100, 570), time.strftime("Live stream   %H:%M:%S"), fill="#a8eacb", font_size=28
            )
        else:
            image = None
            # With one physical output the DXGI primary maps unambiguously to MSS.
            # Multiple-output machines retain explicit MSS monitor selection.
            if os.name == "nt" and len(self._mss.monitors) == 2 and not self._gpu_failed:
                try:
                    if self._gpu is None:
                        import dxcam

                        self._gpu = dxcam.create(output_color="RGB", max_buffer_len=2)
                    pixels = self._gpu.grab(new_frame_only=False)
                    if pixels is not None and pixels.shape[:2] == (
                        bounds["height"],
                        bounds["width"],
                    ):
                        image = Image.fromarray(pixels)
                except Exception:
                    self._gpu_failed = True
                    if self._gpu:
                        self._gpu.release()
                        self._gpu = None
                    logging.getLogger("deskpad").warning(
                        "GPU capture unavailable; using compatible capture"
                    )
            if image is None:
                try:
                    shot = self._mss.grab(bounds)
                except Exception:
                    # A display can disappear between enumeration and capture.
                    # Refresh on this same worker and retry the surviving output.
                    self._display_refresh = 0
                    bounds = self.active_display()
                    shot = self._mss.grab(bounds)
                image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        image.thumbnail((self.width, self.width * 2))
        return image, bounds

    def frame(self):
        image, bounds = self.image()
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.quality)
        self.sequence += 1
        return {
            "type": "frame",
            "sequence": self.sequence,
            "width": image.width,
            "height": image.height,
            "bounds": bounds,
            **self.view_info,
        }, buffer.getvalue()

    def close(self):
        if self._gpu:
            self._gpu.release()
            self._gpu = None
        if self._mss is not None:
            self._mss.close()
            self._mss = None
