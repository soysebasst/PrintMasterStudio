from decimal import Decimal as D
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.core.image_analyzer import Diagnosis
from printmaster.domain.models import FitMode, ImageInfo
from printmaster.domain.quality import QualityLevel
from printmaster.infra.settings import load_settings
from printmaster.ui.widgets.inspector import Inspector
from printmaster.ui.widgets.quality_panel import DropZone, QualityPanel

pytestmark = pytest.mark.ui


@pytest.fixture
def insp(qtbot, settings):
    w = Inspector(settings)
    qtbot.addWidget(w)
    w.show()
    return w


def test_mode_buttons(insp, qtbot):
    qtbot.mouseClick(insp.mode_buttons[FitMode.COVER], Qt.LeftButton)
    assert insp.mode() == FitMode.COVER
    assert insp.mode_buttons[FitMode.COVER].isChecked()
    assert not insp.mode_buttons[FitMode.FIT_LENGTH].isChecked()


def test_advanced_collapsed_and_remembered(insp, qtbot):
    assert not insp.advanced_box.isVisible()
    qtbot.mouseClick(insp.advanced_toggle, Qt.LeftButton)
    assert insp.advanced_box.isVisible()
    assert load_settings().advanced_open is True


def test_price_label(insp):
    insp.set_price(17000)
    assert "$17.000" in insp.price_label.text()


def test_drop_zone_emits(qtbot, tmp_path):
    z = DropZone()
    qtbot.addWidget(z)
    p = tmp_path / "x.png"
    p.write_bytes(b"x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p))])
    with qtbot.waitSignal(z.file_dropped) as blocker:
        z.dropEvent(QDropEvent(QPointF(2, 2), Qt.CopyAction, mime, Qt.LeftButton,
                               Qt.NoModifier))
    assert blocker.args == [p]


def test_quality_chip(qtbot):
    panel = QualityPanel()
    qtbot.addWidget(panel)
    diag = Diagnosis(10.0, QualityLevel.MUY_BAJA, QualityLevel.MUY_BAJA, 5.0, 1.0, 1.0, 89,
                     ("Pocos píxeles para este tamaño: 10 PPI efectivos.",), "Ampliar")
    info = ImageInfo(Path("a.jpg"), "JPEG", 236, 420, "RGB", False, None, 1, 1000, "")
    panel.show_item(diag, info, price=17000, page_mm=(D(600), D(1100)))
    assert panel.level_chip.text() == "Muy baja · 10 PPI"
    assert "Pocos píxeles" in panel.text()
    assert not panel.details.isVisible()


def test_panel_fits_1366x768(qtbot, settings):
    from printmaster.printers.profiles import load_profile
    from printmaster.ui.pages.job_page import JobPage
    page = JobPage(settings, load_profile())
    qtbot.addWidget(page)
    page.resize(1366, 700)
    page.show()
    assert page.side_panel.sizeHint().height() <= 700
