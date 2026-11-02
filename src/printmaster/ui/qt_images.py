"""Conversión de imágenes Pillow a QImage/QPixmap."""

from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage


def pil_to_qimage(img: Image.Image) -> QImage:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(data, rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format_RGBA8888).copy()
