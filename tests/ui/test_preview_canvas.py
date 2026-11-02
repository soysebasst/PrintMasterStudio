from decimal import Decimal as D
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage

from printmaster.core.layout import plan
from printmaster.domain.models import FitMode, ImageInfo, Orientation, PrintSpec
from printmaster.printers.profiles import load_profile
from printmaster.ui.widgets.preview_canvas import PreviewCanvas

pytestmark = pytest.mark.ui


def info(w, h):
    return ImageInfo(Path("x.jpg"), "JPEG", w, h, "RGB", False, None, 1, 0, "")


@pytest.fixture
def canvas(qtbot):
    c = PreviewCanvas()
    qtbot.addWidget(c)
    c.resize(800, 600)
    c.show()
    return c


def show(canvas, mode, w=4000, h=3000, spec=None):
    spec = spec or PrintSpec(D(600), D(900), orientation=Orientation.PORTRAIT)
    p = plan(info(w, h), spec, mode)
    img = QImage(400, 300, QImage.Format_RGB32)
    img.fill(Qt.blue)
    canvas.show_plan(img, p, mode, load_profile(), (w, h))
    return p


def test_page_size_in_points(canvas):
    show(canvas, FitMode.CONTAIN)
    r = canvas.page_item.rect()
    assert abs(r.width() - 1700.79) < 0.5 and abs(r.height() - 2551.18) < 0.5


def test_cover_drag_emits_crop(canvas, qtbot):
    show(canvas, FitMode.COVER)
    vp = canvas.viewport()
    center = vp.rect().center()
    with qtbot.waitSignal(canvas.crop_changed, timeout=1000) as blocker:
        qtbot.mousePress(vp, Qt.LeftButton, pos=center)
        qtbot.mouseMove(vp, center + QPoint(200, 0))
        qtbot.mouseRelease(vp, Qt.LeftButton, pos=center + QPoint(200, 0))
    assert blocker.args[0].x < 0.5


def test_contain_drag_emits_nothing(canvas, qtbot):
    show(canvas, FitMode.CONTAIN)
    vp = canvas.viewport()
    center = vp.rect().center()
    with qtbot.assertNotEmitted(canvas.crop_changed):
        qtbot.mousePress(vp, Qt.LeftButton, pos=center)
        qtbot.mouseMove(vp, center + QPoint(200, 0))
        qtbot.mouseRelease(vp, Qt.LeftButton, pos=center + QPoint(200, 0))


def test_zoom(canvas):
    show(canvas, FitMode.CONTAIN)
    before = canvas.transform().m11()
    canvas.zoom_in()
    assert canvas.transform().m11() > before
    canvas.zoom_out()
    canvas.zoom_out()
    assert canvas.transform().m11() < before


def test_clear(canvas):
    show(canvas, FitMode.CONTAIN)
    canvas.clear()
    assert canvas.page_item is None
