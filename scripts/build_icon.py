"""Rasterize the shared vector mark into a multi-resolution Windows icon."""
import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1]
renderer = QSvgRenderer(str(root / "web/public/icon.svg"))
if not renderer.isValid():
    raise RuntimeError("Invalid Deskpad icon")
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()

buffer = QBuffer()
buffer.open(QIODevice.OpenModeFlag.WriteOnly)
image.save(buffer, "PNG")
output = root / "build/deskpad.ico"
output.parent.mkdir(parents=True, exist_ok=True)
Image.open(io.BytesIO(bytes(buffer.data()))).save(
    output, sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)]
)
