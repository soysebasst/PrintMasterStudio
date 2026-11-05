"""Iconos SVG de trazo, teñidos al color pedido."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_NAMES = ("home", "photo-plus", "settings", "sparkles", "clipboard", "download", "plus",
              "zoom-in", "zoom-out", "maximize", "check", "x", "crop", "rotate")
TEXT = "#ece9f5"


@lru_cache(maxsize=128)
def _svg(name: str) -> str:
    return resources.files("printmaster.ui").joinpath(f"assets/icons/{name}.svg").read_text(
        encoding="utf-8")


def icon(name: str, color: str = TEXT, size: int = 20) -> QIcon:
    data = QByteArray(_svg(name).replace("currentColor", color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    result = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
        painter.end()
        pm.setDevicePixelRatio(scale)
        result.addPixmap(pm)
    return result
