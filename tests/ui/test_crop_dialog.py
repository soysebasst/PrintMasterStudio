import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage

from printmaster.domain.models import CropRect
from printmaster.ui.widgets.crop_dialog import CropDialog, CropView

pytestmark = pytest.mark.ui


def image(w=400, h=200):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(200, 120, 60))
    return img


@pytest.fixture
def view(qtbot):
    v = CropView(image(), CropRect())
    qtbot.addWidget(v)
    v.resize(600, 400)
    v.show()
    return v


def pt(view, fx, fy) -> QPoint:
    d = view.display_rect()
    return QPointF(d.x() + fx * d.width(), d.y() + fy * d.height()).toPoint()


def drag(qtbot, view, a: QPoint, b: QPoint):
    qtbot.mousePress(view, Qt.LeftButton, pos=a)
    qtbot.mouseMove(view, b)
    qtbot.mouseRelease(view, Qt.LeftButton, pos=b)


def test_drag_corner_resizes(view, qtbot):
    drag(qtbot, view, pt(view, 1, 1), pt(view, 0.5, 0.5))
    r = view.crop_rect()
    assert (r.x0, r.y0) == (0.0, 0.0)
    assert r.x1 == pytest.approx(0.5, abs=0.02) and r.y1 == pytest.approx(0.5, abs=0.02)


def test_drag_inside_moves_and_stays_inside(view, qtbot):
    view.set_crop_rect(CropRect(0.0, 0.0, 0.5, 0.5))
    drag(qtbot, view, pt(view, 0.25, 0.25), pt(view, 0.95, 0.95))
    r = view.crop_rect()
    assert r.x1 == pytest.approx(1.0) and r.y1 == pytest.approx(1.0)
    assert r.x1 - r.x0 == pytest.approx(0.5, abs=0.01)


def test_drag_edge_moves_one_side(view, qtbot):
    drag(qtbot, view, pt(view, 0.5, 0), pt(view, 0.5, 0.3))
    r = view.crop_rect()
    assert r.y0 == pytest.approx(0.3, abs=0.02) and (r.x0, r.x1, r.y1) == (0.0, 1.0, 1.0)


def test_aspect_lock_keeps_ratio(view, qtbot):
    view.set_aspect(1.0)  # cuadrado en píxeles: 200x200 de 400x200
    r = view.crop_rect()
    assert (r.x1 - r.x0) * 400 == pytest.approx((r.y1 - r.y0) * 200, rel=0.01)
    drag(qtbot, view, pt(view, r.x1, r.y1), pt(view, r.x1 - 0.2, r.y1 - 0.1))
    r = view.crop_rect()
    assert (r.x1 - r.x0) * 400 == pytest.approx((r.y1 - r.y0) * 200, rel=0.03)


def test_arrow_keys_move(view, qtbot):
    view.set_crop_rect(CropRect(0.2, 0.2, 0.6, 0.6))
    view.setFocus()
    qtbot.keyClick(view, Qt.Key_Right)
    assert view.crop_rect().x0 > 0.2


def test_dialog_presets_reset_and_describe(qtbot):
    seen = []

    def describe(r):
        seen.append(r)
        return f"{r.x1 - r.x0:.2f}"

    dlg = CropDialog(image(), CropRect(0.1, 0.1, 0.9, 0.9),
                     [("Libre", None), ("Original", 2.0), ("60 × 90 cm", 600 / 900)], describe)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.mouseClick(dlg.preset_buttons["60 × 90 cm"], Qt.LeftButton)
    r = dlg.crop_rect()
    assert (r.x1 - r.x0) * 400 / ((r.y1 - r.y0) * 200) == pytest.approx(600 / 900, rel=0.01)
    assert dlg.info_label.text() == describe(r)
    qtbot.mouseClick(dlg.reset_btn, Qt.LeftButton)
    assert dlg.crop_rect().is_full
