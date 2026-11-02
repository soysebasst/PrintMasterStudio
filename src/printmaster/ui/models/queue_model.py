"""Modelo Qt de la cola de imágenes (envuelve JobController.items)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap

from printmaster.app_services.job_controller import JobController
from printmaster.core.image_loader import make_thumbnail
from printmaster.core.pricing import format_cop
from printmaster.ui.qt_images import pil_to_qimage
from printmaster.ui.workers import run_async

StatusRole = Qt.UserRole + 1
LevelRole = Qt.UserRole + 2
EnhancedRole = Qt.UserRole + 3  # "enhancing" | "enhanced" | None


def _placeholder(color: str) -> QIcon:
    pm = QPixmap(96, 96)
    pm.fill(QColor(color))
    return QIcon(pm)


LOADING: QIcon | None = None
BROKEN: QIcon | None = None


def _icons() -> tuple[QIcon, QIcon]:
    global LOADING, BROKEN
    if LOADING is None:
        LOADING = _placeholder("#2b2d31")
        BROKEN = _placeholder("#5a2323")
    return LOADING, BROKEN


class QueueModel(QAbstractListModel):
    def __init__(self, controller: JobController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._thumbs: dict[Path, QIcon] = {}
        self._pending: set[Path] = set()
        _icons()

    # --- lectura --------------------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.controller.items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.controller.items):
            return None
        item = self.controller.items[index.row()]
        if role == Qt.DisplayRole:
            return item.path.name
        if role == Qt.DecorationRole:
            if item.info is None:
                return BROKEN
            return self._thumbs.get(item.path, LOADING)
        if role == Qt.ToolTipRole:
            if item.info is None:
                return item.error or "No se pudo leer."
            info = item.info
            tip = (f"{info.format} · {info.width_px}×{info.height_px} px · "
                   f"{info.file_size / 1_048_576:.1f} MB")
            price = self.controller.price_for(index.row())
            if price is not None:
                w, h = (f"{(v / 10).normalize():f}" for v in
                        self.controller.page_size_for(index.row()))
                tip += f"\nLámina {w} × {h} cm · {format_cop(price)}"
            if item.uses_enhanced:
                tip += "\nMejorada con IA"
            if item.duplicate_of is not None:
                tip += f"\nDuplicado de #{item.duplicate_of + 1}"
            if item.error:
                tip += f"\n{item.error}"
            return tip
        if role == StatusRole:
            return item.status
        if role == LevelRole:
            return item.diagnosis.level if item.diagnosis else None
        if role == EnhancedRole:
            if item.enhancing:
                return "enhancing"
            return "enhanced" if item.uses_enhanced else None
        return None

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        if index.isValid():
            return base | Qt.ItemIsDragEnabled
        return base | Qt.ItemIsDropEnabled

    def supportedDropActions(self):  # noqa: N802
        return Qt.MoveAction

    # --- escritura ------------------------------------------------------------------
    def refresh(self, row: int | None = None) -> None:
        if row is None:
            # dataChanged (no reset) para conservar la selección actual
            if self.rowCount():
                self.dataChanged.emit(self.index(0), self.index(self.rowCount() - 1))
        elif 0 <= row < self.rowCount():
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)

    def add_paths(self, paths: list[Path]) -> list[int]:
        first = self.rowCount()
        before = len(self.controller.items)
        new = self.controller.add_paths(paths)
        if not new:
            return new
        self.beginInsertRows(QModelIndex(), first, first + len(new) - 1)
        self.endInsertRows()
        assert len(self.controller.items) == before + len(new)
        for i in new:
            self._request_thumbnail(self.controller.items[i].path)
        return new

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            self.controller.remove([row])
            self.endRemoveRows()

    def moveRows(self, src_parent, src_row, count, dst_parent, dst_child) -> bool:  # noqa: N802
        if count != 1 or src_row == dst_child or src_row + 1 == dst_child:
            return False
        if not self.beginMoveRows(src_parent, src_row, src_row, dst_parent, dst_child):
            return False
        dst = dst_child if dst_child < src_row else dst_child - 1
        self.controller.move(src_row, dst)
        self.endMoveRows()
        return True

    # --- miniaturas -----------------------------------------------------------------
    def _request_thumbnail(self, path: Path) -> None:
        if path in self._thumbs or path in self._pending:
            return
        self._pending.add(path)
        run_async(make_thumbnail, path, 192,
                  on_done=lambda img, p=path: self._thumb_ready(p, img),
                  on_failed=lambda msg, p=path: self._thumb_failed(p), owner=self)

    def _thumb_ready(self, path: Path, img) -> None:
        self._pending.discard(path)
        self._thumbs[path] = QIcon(QPixmap.fromImage(pil_to_qimage(img)))
        self._emit_for(path)

    def _thumb_failed(self, path: Path) -> None:
        self._pending.discard(path)
        self._thumbs[path] = BROKEN
        self._emit_for(path)

    def _emit_for(self, path: Path) -> None:
        for row, item in enumerate(self.controller.items):
            if item.path == path:
                self.refresh(row)
