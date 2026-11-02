"""Punto de arranque de la aplicación de escritorio."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from printmaster.infra.logging_setup import setup_logging
from printmaster.infra.settings import load_settings
from printmaster.ui.main_window import MainWindow
from printmaster.ui.theme import apply_dark_theme


def _install_excepthook() -> None:
    log = logging.getLogger("printmaster")

    def hook(exc_type, exc, tb):
        log.critical("Error no controlado", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None:
            QMessageBox.critical(None, "PrintMaster Studio",
                                 "Ocurrió un error inesperado. Detalles en el registro.")

    sys.excepthook = hook


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PrintMaster Studio")
    setup_logging()
    _install_excepthook()
    apply_dark_theme(app)
    window = MainWindow(load_settings())
    window.show()
    return app.exec()
