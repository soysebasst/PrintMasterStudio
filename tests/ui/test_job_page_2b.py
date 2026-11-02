import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QGuiApplication

from printmaster.core.enhance.gemini_web import DEFAULT_PROMPT, GEMINI_URL
from printmaster.domain.models import ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings, monkeypatch):
    settings.enhance_enabled = False
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1366, 740)
    p.show()
    p.messages, p.opened, p.revealed = [], [], []
    p._info = lambda title, text: p.messages.append(text)
    p._open_url = lambda url: p.opened.append(url)
    p._reveal = lambda path: p.revealed.append(path)
    return p


def drop(page, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(x)) for x in paths])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))


def load_respeto(page, qtbot, make_image, tmp_path):
    src = make_image("respeto.jpg", size=(236, 420), folder=tmp_path / "in")
    drop(page, [src])
    qtbot.waitUntil(lambda: page.controller.items and
                    page.controller.items[0].status == ItemStatus.READY, timeout=10000)
    return src


def test_gemini_button(page, qtbot, make_image, tmp_path):
    src = load_respeto(page, qtbot, make_image, tmp_path)
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    assert QGuiApplication.clipboard().text() == DEFAULT_PROMPT
    assert page.opened == [GEMINI_URL] and page.revealed == [src]
    assert "Prompt copiado" in page.next_label.text()


def test_drop_gemini_result(page, qtbot, make_image, tmp_path):
    load_respeto(page, qtbot, make_image, tmp_path)
    g = tmp_path / "descargas" / "gemini.png"
    g.parent.mkdir()
    Image.new("RGB", (2304, 4096), (240, 200, 120)).save(g)  # liviana: CI es lento
    page.quality.drop_zone.file_dropped.emit(g)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=60000)
    qtbot.waitUntil(lambda: "Gemini" in page.diagnosis.text(), timeout=5000)
    assert "$17.000" in page.total_label.text()
    assert page.enhanced_btn.isEnabled() and page.enhanced_btn.isChecked()
    qtbot.mouseClick(page.original_btn, Qt.LeftButton)
    assert page._show_original is True
    page.controller.approve(0)
    page._update_state()
    assert page.export_btn.text() == "Exportar 1 PDF"


def test_bad_drop_shows_message(page, qtbot, make_image, tmp_path):
    load_respeto(page, qtbot, make_image, tmp_path)
    bad = tmp_path / "roto.png"
    bad.write_bytes(b"x" * 40)
    page.quality.drop_zone.file_dropped.emit(bad)
    qtbot.waitUntil(lambda: any("No se pudo usar" in m for m in page.messages), timeout=5000)
    assert page.controller.items[0].enhanced is None


def test_next_label_states(page, qtbot, make_image, tmp_path):
    assert page.next_label.text().endswith("Arrastra o agrega las imágenes del cliente")
    load_respeto(page, qtbot, make_image, tmp_path)
    qtbot.waitUntil(lambda: "Mejora «respeto.jpg»" in page.next_label.text(), timeout=5000)


def test_progress_hidden_when_idle(page):
    assert not page.progress.isVisible()


def test_step_chips(page, qtbot, make_image, tmp_path):
    assert [c.text() for c in page.step_chips] == ["1  Cargar", "2  Revisar", "3  Exportar"]
