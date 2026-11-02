"""Página de inicio."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printmaster.infra.settings import FavoriteFormat, Settings


class HomePage(QWidget):
    new_job_requested = Signal()
    favorite_chosen = Signal(object)  # FavoriteFormat

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        title = QLabel("PrintMaster Studio")
        title.setObjectName("title")
        lay.addWidget(title)
        lay.addWidget(QLabel("Prepare imágenes y genere un PDF por imagen con medidas exactas."))
        self.new_job_btn = QPushButton("＋  Nuevo trabajo")
        self.new_job_btn.setObjectName("home_new_job")
        self.new_job_btn.setProperty("primary", True)
        self.new_job_btn.setMinimumHeight(56)
        self.new_job_btn.clicked.connect(self.new_job_requested.emit)
        lay.addWidget(self.new_job_btn)
        lay.addSpacing(16)
        lay.addWidget(QLabel("Formatos favoritos (doble clic para empezar):"))
        self.favorites = QListWidget()
        self.favorites.itemDoubleClicked.connect(self._on_favorite)
        lay.addWidget(self.favorites, 1)
        self.set_favorites(settings.favorites)

    def set_favorites(self, favorites: list[FavoriteFormat]) -> None:
        self.favorites.clear()
        for fav in favorites:
            item = QListWidgetItem(fav.name)
            item.setData(Qt.UserRole, fav)
            self.favorites.addItem(item)

    def _on_favorite(self, item: QListWidgetItem) -> None:
        self.favorite_chosen.emit(item.data(Qt.UserRole))
