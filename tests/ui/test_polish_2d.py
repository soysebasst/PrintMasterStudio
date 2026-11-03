import threading

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QDropEvent, QGuiApplication, QImage

from printmaster.domain.models import CropRect, ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages import job_page as jp
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings, tmp_path):
    settings.downloads_dir = tmp_path / "descargas"
    settings.downloads_dir.mkdir()
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1366, 740)
    p.show()
    p.messages = []
    p._info = lambda title, text: p.messages.append(text)
    p._open_url = lambda url: None
    return p


def load(page, qtbot, make_image, tmp_path, size):
    src = make_image("a.png", size=size, pattern="solid", color=(200, 120, 60),
                     folder=tmp_path / "in")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))
    qtbot.waitUntil(lambda: page.controller.items and
                    page.controller.items[0].status == ItemStatus.READY, timeout=10000)
    page.queue.list.setCurrentIndex(page.model.index(0))


def test_copy_for_gemini_decodes_in_background(page, qtbot, make_image, tmp_path, monkeypatch):
    load(page, qtbot, make_image, tmp_path, (300, 200))
    threads = []
    real = jp.load_proxy

    def spy(path, max_side=2048):
        threads.append(threading.current_thread())
        return real(path, max_side)

    monkeypatch.setattr(jp, "load_proxy", spy)
    QGuiApplication.clipboard().setText("antes")
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: page._copying is None, timeout=10000)
    qtbot.waitUntil(lambda: not QGuiApplication.clipboard().image().isNull(), timeout=10000)
    assert threads and threads[0] is not threading.main_thread()
    assert page._waiting is not None
    assert "Imagen copiada" in page.next_label.text()


def test_smaller_result_warns_to_download(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (2000, 3000))
    g = tmp_path / "g.png"
    Image.new("RGB", (765, 1024), (240, 200, 120)).save(g)
    page._on_external_dropped(g)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    qtbot.waitUntil(lambda: any("más pequeña" in m for m in page.messages), timeout=5000)
    assert any("descargue" in m.lower() for m in page.messages)


def test_pasted_preview_size_suggests_download(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (300, 400))  # original aún más pequeña
    img = QImage(765, 1024, QImage.Format_RGB32)
    img.fill(QColor(240, 200, 120))
    QGuiApplication.clipboard().setImage(img)
    qtbot.mouseClick(page.quality.paste_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    qtbot.waitUntil(lambda: any("descargue" in m.lower() for m in page.messages), timeout=5000)


def test_big_result_no_warning(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (300, 400))
    g = tmp_path / "g.png"
    Image.new("RGB", (1536, 2048), (240, 200, 120)).save(g)
    page._on_external_dropped(g)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    qtbot.wait(100)
    assert page.messages == []


def test_price_card_visible_and_follows_crop(page, qtbot, make_image, tmp_path):
    assert not page.quality.price_card.isVisibleTo(page)
    load(page, qtbot, make_image, tmp_path, (1000, 1500))
    assert page.quality.price_card.isVisibleTo(page)
    assert page.quality.price_value.text() == "$15.000"
    assert "60 × 90 cm" in page.quality.price_detail.text()
    page._run_crop_dialog = lambda dlg: CropRect(0.0, 0.0, 1.0, 0.5)
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    assert page.quality.price_value.text() == "$10.000"
    assert "60 × 45 cm" in page.quality.price_detail.text()


def test_use_original_instead_of_gemini(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (2000, 3000))
    g = tmp_path / "g.png"
    Image.new("RGB", (765, 1024), (240, 200, 120)).save(g)
    page._on_external_dropped(g)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    qtbot.waitUntil(lambda: page.quality.use_original_btn.isVisibleTo(page), timeout=5000)
    qtbot.mouseClick(page.quality.use_original_btn, Qt.LeftButton)
    item = page.controller.items[0]
    assert not item.uses_enhanced
    assert page.quality.use_original_btn.text().strip() == "Usar la de Gemini"
    qtbot.mouseClick(page.quality.use_original_btn, Qt.LeftButton)
    assert item.uses_enhanced
