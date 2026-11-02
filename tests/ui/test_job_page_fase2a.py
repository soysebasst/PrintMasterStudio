import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.domain.models import ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings, fake_engine_cmd, tmp_path):
    p = JobPage(settings, load_profile(),
                enhancer=Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache"))
    qtbot.addWidget(p)
    p.resize(1300, 800)
    p.show()
    p.messages = []
    p._info = lambda title, text: p.messages.append(text)
    return p


def drop(page, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(x)) for x in paths])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))


def test_enhance_flow_ui(page, qtbot, make_image, tmp_path):
    drop(page, [make_image("respeto.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    qtbot.waitUntil(lambda: "Mejorada con IA" in page.diagnosis.text(), timeout=5000)
    assert "$17.000" in page.total_label.text() and "1 lámina" in page.total_label.text()
    assert page.before_after_btn.isEnabled()
    before = page.before_after_btn.text()
    qtbot.mouseClick(page.before_after_btn, Qt.LeftButton)
    assert page.before_after_btn.text() != before
    assert not page.cancel_enhance_btn.isVisible()


def test_export_disabled_while_enhancing(page, qtbot, make_image, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "2")
    drop(page, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhancing, timeout=10000)
    page.controller.approve(0)
    page._update_state()
    assert not page.export_btn.isEnabled()
    assert page.cancel_enhance_btn.isVisible()


def test_cancel_enhance(page, qtbot, make_image, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "5")
    drop(page, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhancing, timeout=10000)
    qtbot.mouseClick(page.cancel_enhance_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: not page.controller.items[0].enhancing, timeout=3000)
    item = page.controller.items[0]
    assert item.enhanced is None and item.status == ItemStatus.READY
    qtbot.waitUntil(lambda: not page.cancel_enhance_btn.isVisible(), timeout=2000)


def test_no_enhance_when_disabled(qtbot, settings, fake_engine_cmd, tmp_path, make_image):
    settings.enhance_enabled = False
    p = JobPage(settings, load_profile(),
                enhancer=Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache"))
    qtbot.addWidget(p)
    drop(p, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: p.controller.items[0].status == ItemStatus.READY, timeout=10000)
    qtbot.wait(500)
    assert p.controller.items[0].enhanced is None
