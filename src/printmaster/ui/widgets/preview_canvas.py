"""Vista previa de la página a escala, dibujada desde el mismo RenderPlan que el PDF.

Unidades de escena = puntos PDF. El eje Y se invierte (en PDF crece hacia arriba).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from printmaster.core.layout import full_image_rect_pt
from printmaster.domain.models import BackgroundKind, CropOffset, FitMode, RenderPlan
from printmaster.domain.units import mm_to_pt
from printmaster.printers.profiles import PrinterProfile

ZOOM_STEP = 1.25


def _fmt_cm(mm) -> str:
    value = mm / 10
    return f"{value.normalize():f}".replace(".", ",")


class PreviewCanvas(QGraphicsView):
    crop_changed = Signal(object)  # CropOffset

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#110f17"))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.page_item: QGraphicsRectItem | None = None
        self.image_item: QGraphicsPixmapItem | None = None
        self._plan: RenderPlan | None = None
        self._mode: FitMode | None = None
        self._img_size: tuple[int, int] = (1, 1)
        self._drag_start: QPointF | None = None
        self._image_start: QPointF | None = None
        self._overflow = (0.0, 0.0)
        self._crop_start = CropOffset()

    # --- dibujo ---------------------------------------------------------------------
    def clear(self) -> None:
        self.scene().clear()
        self.page_item = None
        self.image_item = None
        self._plan = None

    def _to_scene(self, rect, page_h: float) -> QRectF:
        x, y, w, h = rect
        return QRectF(x, page_h - y - h, w, h)

    def show_plan(self, proxy: QImage, plan: RenderPlan, mode: FitMode,
                  profile: PrinterProfile, img_size: tuple[int, int]) -> None:
        keep_zoom = self._plan is not None and self._same_page(plan)
        old_transform = self.transform()
        self.clear()
        self._plan, self._mode, self._img_size = plan, mode, img_size
        scene = self.scene()
        pw, ph = plan.page_w_pt, plan.page_h_pt

        self.page_item = QGraphicsRectItem(0, 0, pw, ph)
        self.page_item.setBrush(QBrush(QColor("white")))
        self.page_item.setPen(QPen(Qt.NoPen))
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.page_item.setGraphicsEffect(shadow)
        scene.addItem(self.page_item)

        if plan.background.kind == BackgroundKind.COLOR:
            bg = scene.addRect(0, 0, pw, ph, QPen(Qt.NoPen), QBrush(QColor(*plan.background.color)))
            bg.setZValue(1)

        pixmap = QPixmap.fromImage(proxy)
        W, H = img_size
        if plan.compose_page:
            blur = QGraphicsPixmapItem(pixmap)
            s = max(pw / pixmap.width(), ph / pixmap.height())
            blur.setScale(s)
            blur.setPos((pw - pixmap.width() * s) / 2, (ph - pixmap.height() * s) / 2)
            blur.setOpacity(0.35)
            blur.setZValue(1)
            scene.addItem(blur)
            scale = min(pw / W, ph / H)
            rect = QRectF((pw - W * scale) / 2, (ph - H * scale) / 2, W * scale, H * scale)
        elif mode == FitMode.COVER:
            rect = self._to_scene(full_image_rect_pt(plan, W, H), ph)
        else:
            rect = self._to_scene(plan.dest_rect_pt, ph)

        self.image_item = QGraphicsPixmapItem(pixmap)
        self.image_item.setTransformationMode(Qt.SmoothTransformation)
        self.image_item.setTransform(self.image_item.transform().fromScale(
            rect.width() / pixmap.width(), rect.height() / pixmap.height()))
        self.image_item.setPos(rect.topLeft())
        self.image_item.setZValue(2)
        scene.addItem(self.image_item)

        if mode == FitMode.COVER:
            path = QPainterPath()
            path.addRect(rect.adjusted(-2, -2, 2, 2))
            inner = QPainterPath()
            inner.addRect(QRectF(0, 0, pw, ph))
            veil = QGraphicsPathItem(path.subtracted(inner))
            veil.setBrush(QBrush(QColor(0, 0, 0, 153)))
            veil.setPen(QPen(Qt.NoPen))
            veil.setZValue(3)
            scene.addItem(veil)
            l, t, r, b = plan.src_box
            sw, sh = r - l, b - t
            self._crop_start = CropOffset(l / (W - sw) if W > sw else 0.5,
                                          t / (H - sh) if H > sh else 0.5)
            self._overflow = (rect.width() - pw, rect.height() - ph)
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()

        margin = mm_to_pt(profile.side_margin_mm)
        pen = QPen(QColor("#e07b24"))
        pen.setStyle(Qt.DashLine)
        pen.setCosmetic(True)
        for x in (margin, pw - margin):
            line = scene.addLine(x, 0, x, ph, pen)
            line.setZValue(4)

        label = QGraphicsSimpleTextItem(f"{_fmt_cm(plan.page_w_mm)} × {_fmt_cm(plan.page_h_mm)} cm")
        label.setBrush(QBrush(QColor("#cfd3da")))
        label.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations)
        label.setPos(0, ph + 8)
        scene.addItem(label)

        pad = max(pw, ph) * 0.08
        scene.setSceneRect(QRectF(-pad, -pad, pw + 2 * pad, ph + 2 * pad))
        if keep_zoom:
            self.setTransform(old_transform)
        else:
            self.fit()

    def _same_page(self, plan: RenderPlan) -> bool:
        assert self._plan is not None
        return (abs(self._plan.page_w_pt - plan.page_w_pt) < 1e-6
                and abs(self._plan.page_h_pt - plan.page_h_pt) < 1e-6)

    # --- zoom -----------------------------------------------------------------------
    def fit(self) -> None:
        if self.page_item is not None:
            self.resetTransform()
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)

    def zoom_in(self) -> None:
        self.scale(ZOOM_STEP, ZOOM_STEP)

    def zoom_out(self) -> None:
        self.scale(1 / ZOOM_STEP, 1 / ZOOM_STEP)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.angleDelta().y() > 0:
            self.zoom_in()
        elif event.angleDelta().y() < 0:
            self.zoom_out()

    # --- arrastre del recorte -------------------------------------------------------
    def _can_drag(self) -> bool:
        return self._mode == FitMode.COVER and self.image_item is not None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._can_drag() and event.button() == Qt.LeftButton:
            self._drag_start = self.mapToScene(event.position().toPoint())
            self._image_start = self.image_item.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def _constrained_delta(self, pos: QPointF) -> QPointF:
        delta = pos - self._drag_start
        ox, oy = self._overflow
        x0, y0 = self._crop_start.x * ox, self._crop_start.y * oy
        dx = min(max(delta.x(), -(ox - x0)), x0) if ox > 0 else 0.0
        dy = min(max(delta.y(), -(oy - y0)), y0) if oy > 0 else 0.0
        return QPointF(dx, dy)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None:
            d = self._constrained_delta(self.mapToScene(event.position().toPoint()))
            self.image_item.setPos(self._image_start + d)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None:
            d = self._constrained_delta(self.mapToScene(event.position().toPoint()))
            self._drag_start = None
            self.setCursor(Qt.OpenHandCursor)
            ox, oy = self._overflow
            new_x = self._crop_start.x - (d.x() / ox if ox > 0 else 0.0)
            new_y = self._crop_start.y - (d.y() / oy if oy > 0 else 0.0)
            if d.x() or d.y():
                self.crop_changed.emit(CropOffset(new_x, new_y))
            event.accept()
            return
        super().mouseReleaseEvent(event)
