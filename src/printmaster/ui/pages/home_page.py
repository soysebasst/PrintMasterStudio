"""Página de inicio."""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printmaster.infra.settings import FavoriteFormat, Settings
from printmaster.ui.icons import icon

FAVORITE_COLUMNS = 4


class HomePage(QWidget):
    new_job_requested = Signal()
    favorite_chosen = Signal(object)  # FavoriteFormat

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(10)
        title = QLabel("Hola")
        title.setObjectName("title")
        lay.addWidget(title)
        sub = QLabel("Prepare imágenes y genere un PDF por imagen con medidas exactas.")
        sub.setObjectName("muted")
        lay.addWidget(sub)
        lay.addSpacing(14)
        self.new_job_btn = QPushButton("  Nuevo trabajo\n  Cargue las imágenes del cliente")
        self.new_job_btn.setObjectName("home_new_job")
        self.new_job_btn.setProperty("primary", True)
        self.new_job_btn.setIcon(icon("photo-plus", "#ffffff", 28))
        self.new_job_btn.setIconSize(QSize(28, 28))
        self.new_job_btn.setMinimumHeight(84)
        self.new_job_btn.setMaximumWidth(520)
        self.new_job_btn.setStyleSheet(
            "QPushButton { border-radius: 14px; font-size: 12pt; text-align: left;"
            " padding: 14px 22px; }")
        self.new_job_btn.clicked.connect(self.new_job_requested.emit)
        lay.addWidget(self.new_job_btn)
        lay.addSpacing(22)
        fav_title = QLabel("Formatos favoritos")
        fav_title.setObjectName("sectionTitle")
        lay.addWidget(fav_title)
        hint = QLabel("Un clic abre un trabajo nuevo con ese tamaño.")
        hint.setObjectName("hint")
        lay.addWidget(hint)
        self._fav_host = QWidget()
        self._fav_grid = QGridLayout(self._fav_host)
        self._fav_grid.setContentsMargins(0, 6, 0, 0)
        self._fav_grid.setHorizontalSpacing(10)
        self._fav_grid.setVerticalSpacing(10)
        lay.addWidget(self._fav_host)
        lay.addStretch(1)
        self.favorite_buttons: list[QPushButton] = []
        self.set_favorites(settings.favorites)

    def set_favorites(self, favorites: list[FavoriteFormat]) -> None:
        for btn in self.favorite_buttons:
            self._fav_grid.removeWidget(btn)
            btn.deleteLater()
        self.favorite_buttons = []
        for n, fav in enumerate(favorites):
            btn = QPushButton(fav.name)
            btn.setObjectName("favoriteChip")
            btn.clicked.connect(lambda _=False, f=fav: self.favorite_chosen.emit(f))
            self._fav_grid.addWidget(btn, n // FAVORITE_COLUMNS, n % FAVORITE_COLUMNS)
            self.favorite_buttons.append(btn)
