"""Cola de imágenes en tarjetas: miniatura, nombre, tamaño, precio y estado."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from printmaster.core.enhance.gemini_web import reveal_command
from printmaster.core.image_loader import SUPPORTED_EXTENSIONS
from printmaster.ui.models.queue_model import (
    OriginRole,
    QueueModel,
    SizePriceRole,
    StatusTextRole,
)

CARD = QSize(156, 196)
THUMB_H = 104

STATUS_COLORS = {  # (fondo, texto)
    "Error": ("#3d1f22", "#ff8a8a"),
    "PDF listo": ("#1d2f4a", "#8ab4ff"),
    "Aprobada": ("#1b3326", "#7ee787"),
    "Mejorando…": ("#2e2440", "#c9a7ff"),
    "Mejorar": ("#3a3018", "#f0c15a"),
    "Lista": ("#1b3326", "#7ee787"),
    "Analizando…": ("#2a2c31", "#a8adb5"),
}
ORIGIN_COLORS = {"IA": "#7c4dcc", "Gemini": "#1f6feb", "Básica": "#5a5f68"}


class CardDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return CARD

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.State_Selected)
        painter.setPen(QPen(QColor("#3d8bfd" if selected else "#2c2e33"), 2 if selected else 1))
        painter.setBrush(QColor("#24262b" if selected else "#1d1f23"))
        painter.drawRoundedRect(r, 10, 10)

        thumb_rect = QRect(r.left() + 8, r.top() + 8, r.width() - 16, THUMB_H)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#141517"))
        painter.drawRoundedRect(thumb_rect, 6, 6)
        icon = index.data(Qt.DecorationRole)
        if icon is not None:
            pm = icon.pixmap(QSize(thumb_rect.width(), thumb_rect.height()))
            pm = pm.scaled(thumb_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = thumb_rect.left() + (thumb_rect.width() - pm.width()) // 2
            y = thumb_rect.top() + (thumb_rect.height() - pm.height()) // 2
            painter.drawPixmap(x, y, pm)
        origin = index.data(OriginRole)
        if origin:
            fm = painter.fontMetrics()
            w = fm.horizontalAdvance(origin) + 12
            badge = QRect(thumb_rect.right() - w - 4, thumb_rect.top() + 4, w, 18)
            painter.setBrush(QColor(ORIGIN_COLORS.get(origin, "#5a5f68")))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QColor("white"))
            painter.drawText(badge, Qt.AlignCenter, origin)

        y = thumb_rect.bottom() + 8
        name = index.data(Qt.DisplayRole) or ""
        f = QFont(option.font)
        painter.setFont(f)
        fm = painter.fontMetrics()
        painter.setPen(QColor("#e6e6e6"))
        painter.drawText(QRect(r.left() + 8, y, r.width() - 16, fm.height()), Qt.AlignLeft,
                         fm.elidedText(name, Qt.ElideMiddle, r.width() - 16))
        y += fm.height() + 2
        painter.setPen(QColor("#a8adb5"))
        size_price = index.data(SizePriceRole) or ""
        painter.drawText(QRect(r.left() + 8, y, r.width() - 16, fm.height()), Qt.AlignLeft,
                         fm.elidedText(size_price, Qt.ElideRight, r.width() - 16))
        y += fm.height() + 6
        status = index.data(StatusTextRole) or ""
        bg, fg = STATUS_COLORS.get(status, ("#2a2c31", "#a8adb5"))
        chip_w = fm.horizontalAdvance(status) + 16
        chip = QRect(r.left() + 8, y, chip_w, fm.height() + 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(chip, 5, 5)
        painter.setPen(QColor(fg))
        painter.drawText(chip, Qt.AlignCenter, status)
        painter.restore()


class FileDropListView(QListView):
    """Cuadrícula de tarjetas que acepta archivos soltados desde el Explorador."""

    files_dropped = Signal(list)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
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
        lay.setContentsMargins(12, 12, 8, 12)
        lay.setSpacing(8)

        header = QHBoxLayout()
        self.title = QLabel("0 imágenes")
        self.title.setObjectName("sectionTitle")
        header.addWidget(self.title)
        header.addStretch(1)
        self.add_btn = QPushButton("+ Agregar")
        self.add_btn.setObjectName("linkButton")
        self.add_menu = QMenu(self)
        self.add_files_action = self.add_menu.addAction("Archivos…")
        self.add_folder_action = self.add_menu.addAction("Carpeta…")
        self.add_files_action.triggered.connect(self._choose_files)
        self.add_folder_action.triggered.connect(self._choose_folder)
        self.add_btn.clicked.connect(
            lambda: self.add_menu.exec(self.add_btn.mapToGlobal(QPoint(0, self.add_btn.height()))))
        header.addWidget(self.add_btn)
        lay.addLayout(header)

        self.list = FileDropListView()
        self.list.setModel(model)
        self.list.setViewMode(QListView.IconMode)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setGridSize(CARD)
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(0)
        self.list.setWordWrap(False)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setItemDelegate(CardDelegate(self.list))
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.setDragDropMode(QAbstractItemView.DropOnly)
        self.list.files_dropped.connect(self.add_paths)
        self.list.selectionModel().currentChanged.connect(
            lambda cur, _prev: self.current_changed.emit(cur.row()))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        lay.addWidget(self.list, 1)

        self.empty_hint = QLabel("Arrastra imágenes aquí\no usa «+ Agregar»")
        self.empty_hint.setObjectName("dropHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_hint)

        self.context_menu = QMenu(self)
        self.remove_action = QAction("Quitar", self)
        self.up_action = QAction("Subir", self)
        self.down_action = QAction("Bajar", self)
        self.reveal_action = QAction("Abrir carpeta", self)
        for a in (self.remove_action, self.up_action, self.down_action, self.reveal_action):
            self.context_menu.addAction(a)
        self.remove_action.triggered.connect(self.remove_selected)
        self.up_action.triggered.connect(self.move_up)
        self.down_action.triggered.connect(self.move_down)
        self.reveal_action.triggered.connect(self._reveal_current)
        QShortcut(QKeySequence(Qt.Key_Delete), self.list, activated=self.remove_selected)

        model.rowsInserted.connect(self._update_title)
        model.rowsRemoved.connect(self._update_title)
        model.modelReset.connect(self._update_title)
        self._update_title()

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

    # --- edición --------------------------------------------------------------------
    def _show_menu(self, pos) -> None:
        if self.list.indexAt(pos).isValid():
            self.context_menu.exec(self.list.viewport().mapToGlobal(pos))

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

    def move_up(self) -> None:
        self._move_current(-1)

    def move_down(self) -> None:
        self._move_current(+1)

    def _reveal_current(self) -> None:
        row = self.current_row()
        if 0 <= row < len(self.model.controller.items):
            path = self.model.controller.items[row].path
            try:
                subprocess.Popen(reveal_command(path))  # noqa: S603
            except OSError:
                pass

    def _update_title(self, *args) -> None:
        n = self.model.rowCount()
        self.title.setText(f"{n} imagen" if n == 1 else f"{n} imágenes")
        self.empty_hint.setVisible(n == 0)

    def current_row(self) -> int:
        return self.list.currentIndex().row()
