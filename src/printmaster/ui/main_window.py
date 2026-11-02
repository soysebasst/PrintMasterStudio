"""Ventana principal: barra lateral de navegación y páginas apiladas."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from printmaster.infra.settings import FavoriteFormat, Settings, save_settings
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.home_page import HomePage
from printmaster.ui.pages.job_page import JobPage
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
        self.home_page.favorite_chosen.connect(self._on_favorite_chosen)
        self.settings_page.settings_changed.connect(self._on_settings_changed)
        self.nav.setCurrentRow(0)

    def _make_job_page(self) -> JobPage:
        page = JobPage(self.settings, self.profile)
        page.favorite_saved.connect(self._on_favorite_saved)
        return page

    def _on_favorite_chosen(self, fav: FavoriteFormat) -> None:
        self.nav.setCurrentRow(1)
        self.job_page.apply_favorite(fav)

    def _on_favorite_saved(self, fav: FavoriteFormat) -> None:
        self.settings.favorites.append(fav)
        save_settings(self.settings)
        self._on_settings_changed(self.settings)
        self.settings_page.set_settings(self.settings)

    def _on_settings_changed(self, settings: Settings) -> None:
        self.settings = settings
        self.home_page.set_favorites(settings.favorites)
        self.job_page.set_settings(settings)
