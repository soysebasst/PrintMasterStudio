"""Cola de imágenes: miniaturas, arrastrar y soltar, reordenar y quitar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from printmaster.core.image_loader import SUPPORTED_EXTENSIONS
from printmaster.domain.models import ItemStatus
from printmaster.domain.quality import QualityLevel
from printmaster.ui.models.queue_model import EnhancedRole, LevelRole, QueueModel, StatusRole

_LEVEL_BADGES = {
    QualityLevel.EXCELENTE: ("● Exc", "#2e9d5b"),
    QualityLevel.BUENA: ("● Bue", "#4caf50"),
    QualityLevel.ACEPTABLE: ("● Ace", "#c9a227"),
    QualityLevel.BAJA: ("▲ Baj", "#e07b24"),
    QualityLevel.MUY_BAJA: ("▲ MBaj", "#d64545"),
}


class BadgeDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        super().paint(painter, option, index)
        enhanced = index.data(EnhancedRole)
        if enhanced:
            painter.save()
            r = option.rect
            ia = QRect(r.right() - 74, r.top() + 26, 40, 18)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#8e44ad"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(ia, 4, 4)
            painter.setPen(QColor("white"))
            text = {"enhancing": "…", "enhanced": "IA", "basic": "Mej."}[enhanced]
            painter.drawText(ia, Qt.AlignCenter, text)
            painter.restore()
        status = index.data(StatusRole)
        level = index.data(LevelRole)
        if status == ItemStatus.ERROR:
            text, color = "✕ Error", "#d64545"
        elif status == ItemStatus.EXPORTED:
            text, color = "✓ PDF", "#3d8bfd"
        elif status == ItemStatus.APPROVED:
            text, color = "✓ Aprob.", "#2e9d5b"
        elif level in _LEVEL_BADGES:
            text, color = _LEVEL_BADGES[level]
        else:
            return
        painter.save()
        r = option.rect
        badge = QRect(r.right() - 74, r.top() + 4, 70, 18)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(QColor("white"))
        painter.drawText(badge, Qt.AlignCenter, text)
        painter.restore()


class FileDropListView(QListView):
    """Lista que reordena internamente y además acepta archivos desde el Explorador."""

    files_dropped = Signal(list)

    def _external(self, event) -> bool:
        return event.mimeData().hasUrls() and event.source() is not self

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._external(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._external(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if self._external(event):
            urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
            self.files_dropped.emit([Path(u.toLocalFile()) for u in urls])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


def _filter_string() -> str:
    exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
    return f"Imágenes ({exts})"


class QueueView(QWidget):
    current_changed = Signal(int)
    paths_added = Signal(list)  # índices nuevos

    def __init__(self, model: QueueModel, parent=None) -> None:
        super().__init__(parent)
        self.model = model
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.title = QLabel("COLA (0)")
        lay.addWidget(self.title)

        self.list = FileDropListView()
        self.list.files_dropped.connect(self.add_paths)
        self.list.setModel(model)
        self.list.setViewMode(QListView.ListMode)
        self.list.setIconSize(QSize(72, 72))
        self.list.setSpacing(2)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setItemDelegate(BadgeDelegate(self.list))
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.selectionModel().currentChanged.connect(
            lambda cur, _prev: self.current_changed.emit(cur.row()))
        lay.addWidget(self.list, 1)

        hint = QLabel("Arrastre aquí imágenes o carpetas")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #8a8f98;")
        lay.addWidget(hint)

        row1 = QHBoxLayout()
        self.add_files_btn = QPushButton("+ Archivos")
        self.add_folder_btn = QPushButton("+ Carpeta")
        row1.addWidget(self.add_files_btn)
        row1.addWidget(self.add_folder_btn)
        lay.addLayout(row1)
        row2 = QHBoxLayout()
        self.up_btn = QPushButton("▲")
        self.up_btn.setToolTip("Subir en la cola")
        self.down_btn = QPushButton("▼")
        self.down_btn.setToolTip("Bajar en la cola")
        self.remove_btn = QPushButton("Quitar")
        self.remove_btn.setToolTip("Quitar de la cola (Supr). No borra el archivo original.")
        for b in (self.up_btn, self.down_btn, self.remove_btn):
            row2.addWidget(b)
        lay.addLayout(row2)

        self.add_files_btn.clicked.connect(self._choose_files)
        self.add_folder_btn.clicked.connect(self._choose_folder)
        self.up_btn.clicked.connect(lambda: self._move_current(-1))
        self.down_btn.clicked.connect(lambda: self._move_current(+1))
        self.remove_btn.clicked.connect(self.remove_selected)
        QShortcut(QKeySequence(Qt.Key_Delete), self.list, activated=self.remove_selected)
        model.rowsInserted.connect(self._update_title)
        model.rowsRemoved.connect(self._update_title)
        model.modelReset.connect(self._update_title)

    # --- entrada de archivos --------------------------------------------------------
    def add_paths(self, paths: list[Path]) -> None:
        new = self.model.add_paths(paths)
        if new:
            if not self.list.currentIndex().isValid():
                self.list.setCurrentIndex(self.model.index(new[0]))
            self.paths_added.emit(new)

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Agregar imágenes", "", _filter_string())
        if files:
            self.add_paths([Path(f) for f in files])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Agregar carpeta")
        if folder:
            self.add_paths([Path(folder)])

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.add_paths([Path(u.toLocalFile()) for u in urls])
            event.acceptProposedAction()

    # --- edición de la cola ---------------------------------------------------------
    def remove_selected(self) -> None:
        rows = [i.row() for i in self.list.selectionModel().selectedIndexes()]
        if not rows and self.list.currentIndex().isValid():
            rows = [self.list.currentIndex().row()]
        if rows:
            self.model.remove_rows(rows)

    def _move_current(self, delta: int) -> None:
        row = self.list.currentIndex().row()
        target = row + delta
        if row < 0 or not (0 <= target < self.model.rowCount()):
            return
        dst_child = target + 1 if delta > 0 else target
        if self.model.moveRows(QModelIndex(), row, 1, QModelIndex(), dst_child):
            self.list.setCurrentIndex(self.model.index(target))

    def _update_title(self, *args) -> None:
        self.title.setText(f"COLA ({self.model.rowCount()})")

    def current_row(self) -> int:
        return self.list.currentIndex().row()
