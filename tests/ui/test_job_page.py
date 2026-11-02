from datetime import date
from decimal import Decimal as D

import pytest
from pypdf import PdfReader
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.domain.models import ItemStatus
from printmaster.domain.units import Unit, mm_to_pt
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings):
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1300, 800)
    p.show()
    p.messages = []
    p._info = lambda title, text: p.messages.append(text)
    p._export_finished = lambda ok, err, folder: p.messages.append((ok, err, folder))
    return p


def drop(page, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(x)) for x in paths])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))


def all_ready(page, n):
    items = page.controller.items
    return len(items) == n and all(it.status == ItemStatus.READY for it in items)


def test_full_flow(page, qtbot, make_image, tmp_path, settings):
    files = [make_image(f"f{i}.jpg", size=(1200, 1800), seed=i, folder=tmp_path / "in")
             for i in range(2)]
    files.append(make_image("chica.jpg", size=(300, 200), seed=7, folder=tmp_path / "in"))
    page.inspector.set_spec_values(D(100), D(150), Unit.CM)
    qtbot.wait(300)
    drop(page, files)
    qtbot.waitUntil(lambda: all_ready(page, 3), timeout=10000)
    qtbot.mouseClick(page.approve_all_btn, Qt.LeftButton)
    assert any("Se omitieron 1 imágenes" in m for m in page.messages if isinstance(m, str))
    assert page.export_btn.isEnabled()
    qtbot.mouseClick(page.export_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: any(isinstance(m, tuple) for m in page.messages), timeout=15000)
    ok, err, folder = next(m for m in page.messages if isinstance(m, tuple))
    assert (ok, err) == (2, 0)
    pdfs = sorted((settings.output_dir / date.today().isoformat()).glob("*.pdf"))
    assert len(pdfs) == 2
    spec = page.inspector.spec().resolved_for(1200, 1800)
    box = PdfReader(str(pdfs[0])).pages[0].mediabox
    assert abs(float(box.width) - mm_to_pt(spec.width_mm)) < 0.01
    assert abs(float(box.height) - mm_to_pt(spec.height_mm)) < 0.01
    assert page.progress.value() == 100


def test_invalid_format_disables_export(page, qtbot, make_image, tmp_path):
    drop(page, [make_image("a.jpg", size=(1000, 1000), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: all_ready(page, 1), timeout=10000)
    page.controller.approve(0)
    page.inspector.set_spec_values(D(700), D(700), Unit.CM)
    qtbot.waitUntil(lambda: "Ningún lado" in page.inspector.issues_label.text(), timeout=3000)
    assert not page.export_btn.isEnabled()


def test_approve_selected(page, qtbot, make_image, tmp_path):
    page.inspector.set_spec_values(D(100), D(150), Unit.CM)
    qtbot.wait(300)
    drop(page, [make_image("a.jpg", size=(1200, 1800), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: all_ready(page, 1), timeout=10000)
    qtbot.mouseClick(page.approve_btn, Qt.LeftButton)
    assert page.controller.items[0].status == ItemStatus.APPROVED
    assert "④" in page.steps_label.text()


def test_param_change_keeps_selection_and_preview(page, qtbot, make_image, tmp_path):
    from printmaster.domain.models import FitMode
    drop(page, [make_image(f"a{i}.jpg", size=(1200, 1800), seed=i, folder=tmp_path / "in")
                for i in range(2)])
    qtbot.waitUntil(lambda: all_ready(page, 2), timeout=10000)
    page.queue.list.setCurrentIndex(page.model.index(1))
    qtbot.waitUntil(lambda: page.canvas.page_item is not None, timeout=5000)
    page.inspector.mode_combo.setCurrentIndex(page.inspector.mode_combo.findData(FitMode.COVER))
    qtbot.wait(400)
    assert page.queue.current_row() == 1
    assert page.canvas.page_item is not None
    qtbot.waitUntil(lambda: "Analizando" not in page.diagnosis.text(), timeout=5000)
