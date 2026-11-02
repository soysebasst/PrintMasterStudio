"""Ventana principal: barra lateral de navegación y páginas apiladas."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.home_page import HomePage
from printmaster.ui.pages.settings_page import SettingsPage

SECTIONS = ["Inicio", "Nuevo trabajo", "Configuración"]


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.profile = load_profile(settings.printer_id)
        self.setWindowTitle("PrintMaster Studio")
        self.resize(1366, 800)
        self.setMinimumSize(1100, 650)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.addItems(SECTIONS)
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        lay.addWidget(self.nav)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.home_page = HomePage(settings)
        self.job_page = self._make_job_page()
        self.settings_page = SettingsPage(settings)
        for page in (self.home_page, self.job_page, self.settings_page):
            self.pages.addWidget(page)

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.home_page.new_job_requested.connect(lambda: self.nav.setCurrentRow(1))
        self.settings_page.settings_changed.connect(self._on_settings_changed)
        self.nav.setCurrentRow(0)

    def _make_job_page(self) -> QWidget:
        return QWidget()

    def _on_settings_changed(self, settings: Settings) -> None:
        self.settings = settings
        self.home_page.set_favorites(settings.favorites)
