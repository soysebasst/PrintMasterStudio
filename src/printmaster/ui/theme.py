"""Tema oscuro violeta (estilo Fusion + QSS)."""

from __future__ import annotations

from importlib import resources

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    colors = {
        QPalette.Window: "#15131c", QPalette.WindowText: "#ece9f5",
        QPalette.Base: "#1d1a27", QPalette.AlternateBase: "#252134",
        QPalette.Text: "#ece9f5", QPalette.Button: "#252134",
        QPalette.ButtonText: "#ece9f5", QPalette.Highlight: "#7c5cff",
        QPalette.HighlightedText: "#ffffff", QPalette.ToolTipBase: "#252134",
        QPalette.ToolTipText: "#ece9f5", QPalette.PlaceholderText: "#7d7794",
    }
    for role, color in colors.items():
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    qss = resources.files("printmaster.ui").joinpath("theme.qss").read_text(encoding="utf-8")
    app.setStyleSheet(qss)
