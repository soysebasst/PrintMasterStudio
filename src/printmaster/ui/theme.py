"""Tema oscuro profesional (estilo Fusion + QSS)."""

from __future__ import annotations

from importlib import resources

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    colors = {
        QPalette.Window: "#1e1f22", QPalette.WindowText: "#e6e6e6",
        QPalette.Base: "#2b2d31", QPalette.AlternateBase: "#25272b",
        QPalette.Text: "#e6e6e6", QPalette.Button: "#2f3136",
        QPalette.ButtonText: "#e6e6e6", QPalette.Highlight: "#2f6fdb",
        QPalette.HighlightedText: "#ffffff", QPalette.ToolTipBase: "#2b2d31",
        QPalette.ToolTipText: "#e6e6e6", QPalette.PlaceholderText: "#8a8f98",
    }
    for role, color in colors.items():
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    qss = resources.files("printmaster.ui").joinpath("theme.qss").read_text(encoding="utf-8")
    app.setStyleSheet(qss)
