import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

from printmaster.domain.models import EnhanceChoice, ItemStatus
from printmaster.infra.settings import load_settings, save_settings
from printmaster.printers.profiles import load_profile
from printmaster.ui.main_window import MainWindow
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


def test_advanced_toggle_keeps_saved_prices(qtbot, settings):
    win = MainWindow(settings)
    qtbot.addWidget(win)
    win.show()
    sp = win.settings_page
    sp.price_short_spin.setValue(11111)
    qtbot.mouseClick(sp.save_btn, Qt.LeftButton)
    qtbot.mouseClick(win.job_page.inspector.advanced_toggle, Qt.LeftButton)
    s = load_settings()
    assert s.price_short == 11111 and s.advanced_open is True
    qtbot.mouseClick(sp.save_btn, Qt.LeftButton)
    assert load_settings().advanced_open is True


@pytest.fixture
def page(qtbot, settings):
    settings.enhance_enabled = False
    save_settings(settings)
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1366, 697)
    p.show()
    p.messages = []
    p._info = lambda t, m: p.messages.append(m)
    p._open_url = lambda u: None
    p._reveal = lambda path: None
    return p


def add_respeto(page, qtbot, make_image, tmp_path):
    page.queue.add_paths([make_image("respeto.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].status == ItemStatus.READY, timeout=10000)


def drop_gemini(page, qtbot, tmp_path, size=(2304, 4096)):
    g = tmp_path / "g.png"
    Image.new("RGB", size, (200, 100, 50)).save(g)
    page.quality.drop_zone.file_dropped.emit(g)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=60000)
    qtbot.wait(100)


def test_compare_shows_original_when_no_enhancement(page, qtbot, make_image, tmp_path):
    add_respeto(page, qtbot, make_image, tmp_path)
    assert page.original_btn.isChecked() and not page.enhanced_btn.isEnabled()


def test_combo_synced_after_drop(page, qtbot, make_image, tmp_path):
    add_respeto(page, qtbot, make_image, tmp_path)
    page.inspector.enhance_combo.setCurrentIndex(
        page.inspector.enhance_combo.findData(EnhanceChoice.OFF))
    drop_gemini(page, qtbot, tmp_path)
    assert page.inspector.enhance_combo.currentData() == EnhanceChoice.AUTO


def test_approve_message_names_gemini(page, qtbot, make_image, tmp_path):
    add_respeto(page, qtbot, make_image, tmp_path)
    drop_gemini(page, qtbot, tmp_path)
    page._approve_all()
    text = " ".join(page.messages)
    assert "Gemini" in text and "básica" not in text and "«Original" in text


def test_gemini_hint_clears_on_queue_change(page, qtbot, make_image, tmp_path):
    add_respeto(page, qtbot, make_image, tmp_path)
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: page._copying is None, timeout=10000)
    assert "Imagen copiada" in page.next_label.text()
    page.queue.list.setCurrentIndex(page.model.index(0))
    page.queue.remove_selected()
    assert "Imagen copiada" not in page.next_label.text()


def test_fits_at_697_without_scroll(qtbot, settings, make_image, tmp_path):
    settings.enhance_enabled = False
    win = MainWindow(settings)
    qtbot.addWidget(win)
    win.resize(1366, 697)
    win.show()
    win.nav.setCurrentRow(1)
    page = win.job_page
    page._info = lambda t, m: None
    sa = page.findChildren(QScrollArea)[0]
    qtbot.wait(200)
    assert sa.verticalScrollBar().maximum() == 0
    add_respeto(page, qtbot, make_image, tmp_path)
    drop_gemini(page, qtbot, tmp_path)
    qtbot.wait(200)
    assert sa.verticalScrollBar().maximum() == 0
