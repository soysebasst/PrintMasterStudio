"""Recorte manual estilo celular: marco con esquinas que se arrastran sobre la imagen."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from printmaster.domain.models import MIN_CROP_FRACTION, CropRect

HANDLE_HIT = 22  # px alrededor de esquinas y bordes que cuentan como «agarrar»
CORNER_LEN = 22
MARGIN = 18
KEY_STEP = 0.01
ACCENT = QColor("#7c5cff")


class CropView(QWidget):
    """Muestra la imagen completa y un marco de recorte que se mueve y se estira."""

    changed = Signal(object)  # CropRect

    def __init__(self, image: QImage, rect: CropRect, parent=None) -> None:
        super().__init__(parent)
        self._image = image
        self._r = [rect.x0, rect.y0, rect.x1, rect.y1]
        self._aspect: float | None = None  # ancho/alto en píxeles de la imagen
        self._grab: str | None = None
        self._press = QPointF()
        self._start = list(self._r)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # --- API ------------------------------------------------------------------------
    def crop_rect(self) -> CropRect:
        return CropRect(*self._r)

    def set_crop_rect(self, rect: CropRect) -> None:
        self._r = [rect.x0, rect.y0, rect.x1, rect.y1]
        if self._aspect is not None:
            self._fit_aspect()
        self._emit()

    def set_aspect(self, ratio_px: float | None) -> None:
        """Fija la proporción del marco (ancho/alto en píxeles) o la libera con None."""
        self._aspect = ratio_px
        if ratio_px is not None:
            self._fit_aspect()
        self._emit()

    def display_rect(self) -> QRectF:
        w, h = self._image.width(), self._image.height()
        avail = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        s = min(avail.width() / w, avail.height() / h)
        dw, dh = w * s, h * s
        return QRectF(avail.x() + (avail.width() - dw) / 2,
                      avail.y() + (avail.height() - dh) / 2, dw, dh)

    # --- geometría ------------------------------------------------------------------
    def _norm_aspect(self) -> float:
        """Proporción del marco en fracciones de la imagen."""
        assert self._aspect is not None
        return self._aspect * self._image.height() / self._image.width()

    def _fit_aspect(self) -> None:
        """El marco más grande con la proporción pedida, centrado en el actual."""
        a = self._norm_aspect()
        x0, y0, x1, y1 = self._r
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = x1 - x0, y1 - y0
        if w / h > a:
            w = h * a
        else:
            h = w / a
        if w > 1.0:
            w, h = 1.0, 1.0 / a
        if h > 1.0:
            w, h = a, 1.0
        cx = min(max(cx, w / 2), 1 - w / 2)
        cy = min(max(cy, h / 2), 1 - h / 2)
        self._r = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]

    def _to_norm(self, p: QPointF) -> tuple[float, float]:
        d = self.display_rect()
        return (p.x() - d.x()) / d.width(), (p.y() - d.y()) / d.height()

    def _frame(self) -> QRectF:
        d = self.display_rect()
        x0, y0, x1, y1 = self._r
        return QRectF(d.x() + x0 * d.width(), d.y() + y0 * d.height(),
                      (x1 - x0) * d.width(), (y1 - y0) * d.height())

    def _hit(self, p: QPointF) -> str | None:
        f = self._frame()
        near_l, near_r = abs(p.x() - f.left()) <= HANDLE_HIT, abs(p.x() - f.right()) <= HANDLE_HIT
        near_t, near_b = abs(p.y() - f.top()) <= HANDLE_HIT, abs(p.y() - f.bottom()) <= HANDLE_HIT
        in_x = f.left() - HANDLE_HIT <= p.x() <= f.right() + HANDLE_HIT
        in_y = f.top() - HANDLE_HIT <= p.y() <= f.bottom() + HANDLE_HIT
        if not (in_x and in_y):
            return None
        v = "t" if near_t else "b" if near_b else ""
        h = "l" if near_l else "r" if near_r else ""
        if v and h:
            return v + h
        if self._aspect is None and (v or h):
            return v or h
        return "move" if f.contains(p) else None

    def _apply_drag(self, p: QPointF) -> None:
        nx, ny = self._to_norm(p)
        sx, sy = self._to_norm(self._press)
        dx, dy = nx - sx, ny - sy
        x0, y0, x1, y1 = self._start
        m = MIN_CROP_FRACTION * 2
        g = self._grab or ""
        if g == "move":
            w, h = x1 - x0, y1 - y0
            x0 = min(max(x0 + dx, 0.0), 1.0 - w)
            y0 = min(max(y0 + dy, 0.0), 1.0 - h)
            self._r = [x0, y0, x0 + w, y0 + h]
            return
        if "l" in g:
            x0 = min(max(0.0, x0 + dx), x1 - m)
        if "r" in g:
            x1 = max(min(1.0, x1 + dx), x0 + m)
        if "t" in g:
            y0 = min(max(0.0, y0 + dy), y1 - m)
        if "b" in g:
            y1 = max(min(1.0, y1 + dy), y0 + m)
        if self._aspect is not None:
            a = self._norm_aspect()
            w, h = x1 - x0, y1 - y0
            if w / h > a:  # manda el lado que menos creció: el marco nunca sale de la imagen
                w = h * a
            else:
                h = w / a
            x0, x1 = (x1 - w, x1) if "l" in g else (x0, x0 + w)
            y0, y1 = (y1 - h, y1) if "t" in g else (y0, y0 + h)
        self._r = [x0, y0, x1, y1]

    def _emit(self) -> None:
        self.update()
        self.changed.emit(self.crop_rect())

    # --- eventos --------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        self._grab = self._hit(event.position())
        self._press = event.position()
        self._start = list(self._r)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._grab is None:
            hit = self._hit(event.position())
            cursors = {"move": Qt.SizeAllCursor, "tl": Qt.SizeFDiagCursor,
                       "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                       "bl": Qt.SizeBDiagCursor, "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                       "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor}
            self.setCursor(cursors.get(hit or "", Qt.ArrowCursor))
            return
        self._apply_drag(event.position())
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._grab is not None:
            self._apply_drag(event.position())
            self._grab = None
            self._emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        moves = {Qt.Key_Left: (-KEY_STEP, 0), Qt.Key_Right: (KEY_STEP, 0),
                 Qt.Key_Up: (0, -KEY_STEP), Qt.Key_Down: (0, KEY_STEP)}
        if event.key() not in moves:
            super().keyPressEvent(event)
            return
        dx, dy = moves[event.key()]
        x0, y0, x1, y1 = self._r
        w, h = x1 - x0, y1 - y0
        x0 = min(max(x0 + dx, 0.0), 1.0 - w)
        y0 = min(max(y0 + dy, 0.0), 1.0 - h)
        self._r = [x0, y0, x0 + w, y0 + h]
        self._emit()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        d = self.display_rect()
        p.drawImage(d, self._image)
        f = self._frame()
        veil = QPainterPath()
        veil.addRect(d)
        hole = QPainterPath()
        hole.addRect(f)
        p.fillPath(veil.subtracted(hole), QColor(0, 0, 0, 150))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for k in (1, 2):  # cuadrícula de tercios, como en el celular
            x = f.left() + f.width() * k / 3
            y = f.top() + f.height() * k / 3
            p.drawLine(QPointF(x, f.top()), QPointF(x, f.bottom()))
            p.drawLine(QPointF(f.left(), y), QPointF(f.right(), y))
        p.setPen(QPen(QColor("white"), 1.5))
        p.drawRect(f)
        pen = QPen(ACCENT, 5)
        pen.setCapStyle(Qt.SquareCap)
        p.setPen(pen)
        c = min(CORNER_LEN, f.width() / 3, f.height() / 3)
        for cx, cy, sx, sy in ((f.left(), f.top(), 1, 1), (f.right(), f.top(), -1, 1),
                               (f.left(), f.bottom(), 1, -1), (f.right(), f.bottom(), -1, -1)):
            p.drawLine(QPointF(cx, cy), QPointF(cx + sx * c, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + sy * c))
        if self._aspect is None:
            for mx, my, horiz in ((f.center().x(), f.top(), True),
                                  (f.center().x(), f.bottom(), True),
                                  (f.left(), f.center().y(), False),
                                  (f.right(), f.center().y(), False)):
                if horiz:
                    p.drawLine(QPointF(mx - c / 2, my), QPointF(mx + c / 2, my))
                else:
                    p.drawLine(QPointF(mx, my - c / 2), QPointF(mx, my + c / 2))
        p.end()


class CropDialog(QDialog):
    """Ventana de recorte: proporciones rápidas, vista previa del tamaño y precio."""

    def __init__(self, image: QImage, rect: CropRect,
                 presets: list[tuple[str, float | None]],
                 describe: Callable[[CropRect], str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recortar imagen")
        self.resize(900, 680)
        self._describe = describe
        lay = QVBoxLayout(self)
        hint = QLabel("Arrastre las esquinas o los bordes para elegir qué parte se imprime. "
                      "Arrastre el centro para mover el marco (también con las flechas).")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        lay.addWidget(hint)
        chips = QHBoxLayout()
        chips.addWidget(QLabel("Proporción:"))
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.preset_buttons: dict[str, QPushButton] = {}
        for label, ratio in presets:
            btn = QPushButton(label)
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, r=ratio: self.view.set_aspect(r))
            self._group.addButton(btn)
            chips.addWidget(btn)
            self.preset_buttons[label] = btn
        chips.addStretch(1)
        lay.addLayout(chips)
        self.view = CropView(image, rect)
        lay.addWidget(self.view, 1)
        bottom = QHBoxLayout()
        self.info_label = QLabel("")
        self.info_label.setObjectName("priceLabel")
        bottom.addWidget(self.info_label, 1)
        self.reset_btn = QPushButton("Restablecer")
        self.reset_btn.clicked.connect(self._reset)
        bottom.addWidget(self.reset_btn)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(self.cancel_btn)
        self.apply_btn = QPushButton("Aplicar recorte")
        self.apply_btn.setProperty("primary", True)
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self.accept)
        bottom.addWidget(self.apply_btn)
        lay.addLayout(bottom)
        self.view.changed.connect(self._on_changed)
        first = next(iter(self.preset_buttons.values()), None)
        if first is not None:
            first.setChecked(True)
        self._on_changed(self.view.crop_rect())
        self.view.setFocus()

    def crop_rect(self) -> CropRect:
        return self.view.crop_rect()

    def _reset(self) -> None:
        first = next(iter(self.preset_buttons.values()), None)
        if first is not None:
            first.setChecked(True)
        self.view.set_aspect(None)
        self.view.set_crop_rect(CropRect())

    def _on_changed(self, rect: CropRect) -> None:
        self.info_label.setText(self._describe(rect))
