import pytest
from PySide6.QtCore import Qt

from printmaster.core.enhance import realesrgan
from printmaster.infra.settings import load_settings
from printmaster.ui.pages import settings_page as sp_mod
from printmaster.ui.pages.settings_page import SettingsPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings):
    p = SettingsPage(settings)
    qtbot.addWidget(p)
    p.show()
    return p


def test_save_prices(page, qtbot):
    page.price_long_spin.setValue(20000)
    page.roll_width_spin.setValue(61)
    page.enhance_check.setChecked(False)
    qtbot.mouseClick(page.save_btn, Qt.LeftButton)
    s = load_settings()
    assert s.price_long == 20000 and s.roll_width_mm == 610 and s.enhance_enabled is False


def test_install_engine_button(page, qtbot, monkeypatch, tmp_path):
    fake_exe = tmp_path / "realesrgan-ncnn-vulkan"
    fake_exe.write_text("x")
    monkeypatch.setattr(sp_mod, "install_engine", lambda **k: fake_exe)
    monkeypatch.setattr(realesrgan.RealEsrgan, "self_test", lambda self, d: (True, "Motor listo"))
    with qtbot.waitSignal(page.engine_changed, timeout=5000):
        qtbot.mouseClick(page.install_engine_btn, Qt.LeftButton)
    assert "listo" in page.engine_status_label.text()


def test_engine_status_not_installed(page):
    assert "No instalado" in page.engine_status_label.text()


def test_gemini_prompt_saved(page, qtbot):
    page.gemini_prompt_edit.setPlainText("Mejora esta imagen.")
    qtbot.mouseClick(page.save_btn, Qt.LeftButton)
    assert load_settings().gemini_prompt == "Mejora esta imagen."
    qtbot.mouseClick(page.reset_prompt_btn, Qt.LeftButton)
    assert "letra por letra" in page.gemini_prompt_edit.toPlainText()


def test_save_gemini_options(page, qtbot, tmp_path):
    assert page.gemini_open_combo.currentData() == "desktop"
    page.gemini_open_combo.setCurrentIndex(page.gemini_open_combo.findData("web"))
    page.gemini_url_edit.setText("  https://gemini.google.com/gem/abc  ")
    page.downloads_edit.setText(str(tmp_path / "bajadas"))
    qtbot.mouseClick(page.save_btn, Qt.LeftButton)
    s = load_settings()
    assert s.gemini_open_mode == "web"
    assert s.gemini_url == "https://gemini.google.com/gem/abc"
    assert s.downloads_dir == tmp_path / "bajadas"


def test_empty_gemini_url_restores_default(page, qtbot):
    from printmaster.core.enhance.gemini_web import GEMINI_URL
    page.gemini_url_edit.setText("   ")
    qtbot.mouseClick(page.save_btn, Qt.LeftButton)
    assert load_settings().gemini_url == GEMINI_URL


def test_copy_instructions(page, qtbot):
    from PySide6.QtGui import QGuiApplication
    page.gemini_prompt_edit.setPlainText("Mejora esto")
    qtbot.mouseClick(page.copy_instructions_btn, Qt.LeftButton)
    assert QGuiApplication.clipboard().text() == "Mejora esto"
