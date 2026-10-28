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

    def image(self):
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
            bounds = {"left": 0, "top": 0, "width": 1280, "height": 720}
        else:
            if self._mss is None:
                import mss

                self._mss = mss.mss()
            if not 1 <= self.monitor < len(self._mss.monitors):
                raise RuntimeError(f"Monitor {self.monitor} is unavailable")
            bounds = dict(self._mss.monitors[self.monitor])
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
        }, buffer.getvalue()

    def close(self):
        if self._gpu:
            self._gpu.release()
            self._gpu = None
        if self._mss is not None:
            self._mss.close()
            self._mss = None
