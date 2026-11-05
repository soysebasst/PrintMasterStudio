from decimal import Decimal as D

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.domain.models import CropRect, FitMode, ItemStatus, Orientation
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.home_page import HomePage
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings):
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1366, 740)
    p.show()
    p._info = lambda title, text: None
    return p


def load(page, qtbot, make_image, tmp_path, size):
    src = make_image("a.jpg", size=size, folder=tmp_path / "in")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))
    qtbot.waitUntil(lambda: page.controller.items and
                    page.controller.items[0].status == ItemStatus.READY, timeout=10000)
    page.queue.list.setCurrentIndex(page.model.index(0))
    qtbot.waitUntil(lambda: page.canvas.image_item is not None, timeout=5000)


def test_resolution_and_orientation_not_in_main_window(page, qtbot):
    insp = page.inspector
    if not insp.advanced_box.isVisibleTo(page):
        qtbot.mouseClick(insp.advanced_toggle, Qt.LeftButton)
    assert insp.advanced_box.isVisibleTo(page)
    assert not insp.ppi_combo.isVisibleTo(page) and not insp.ppi_spin.isVisibleTo(page)
    assert not insp.orientation_combo.isVisibleTo(page)
    assert insp.spec().orientation == Orientation.AS_ENTERED


def test_resolution_follows_settings(page, settings):
    settings.default_ppi = 150
    page.set_settings(settings)
    assert page.inspector.spec().ppi == 150


def test_typing_length_in_auto_switches_to_fill(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (1000, 1022))
    insp = page.inspector
    assert insp.mode() == FitMode.FIT_LENGTH and not insp.height_spin.isReadOnly()
    insp.height_spin.setValue(55.0)
    qtbot.waitUntil(lambda: page.controller.mode == FitMode.COVER, timeout=3000)
    assert page.controller.spec.height_mm == D(550)
    assert page.controller.page_size_for(0) == (600, 550)


def test_rotate_button(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (1500, 1000))
    assert not page.rotate_btn.isChecked()
    w0 = page.canvas.image_item.pixmap().width()
    qtbot.mouseClick(page.rotate_btn, Qt.LeftButton)
    assert page.controller.rotated(0) and page.rotate_btn.isChecked()
    assert page.controller.page_size_for(0) == (600, 900)
    qtbot.waitUntil(lambda: page.canvas.image_item.pixmap().width() < w0, timeout=5000)
    assert "Girada" in page.info_label.text()


def test_auto_rotation_shows_checked(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (1500, 1000))
    page.inspector.mode_buttons[FitMode.CONTAIN].click()
    page.inspector.set_spec_values(D(600), D(900), page.inspector._unit)
    qtbot.waitUntil(lambda: page.controller.mode == FitMode.CONTAIN and
                    page.controller.spec.height_mm == D(900), timeout=3000)
    assert page.controller.rotated(0) and page.rotate_btn.isChecked()


def test_crop_dialog_uses_rotated_view(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (1500, 1000))
    qtbot.mouseClick(page.rotate_btn, Qt.LeftButton)
    seen = []
    page._run_crop_dialog = lambda dlg: (seen.append(dlg), CropRect(0.0, 0.0, 1.0, 0.5))[1]
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    img = seen[0].view._image
    assert img.width() < img.height()  # se recorta sobre la imagen ya girada
    assert page.controller.page_size_for(0) == (600, 450)


def test_home_only_new_job_button(qtbot, settings):
    home = HomePage(settings)
    qtbot.addWidget(home)
    home.show()
    assert home.new_job_btn.isVisibleTo(home)
    assert not home.title_label.isVisibleTo(home) and not home.favorites_box.isVisibleTo(home)


def test_custom_ppi_spin_stays_hidden(qtbot, settings):
    settings.default_ppi = 180
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.show()
    insp = p.inspector
    if not insp.advanced_box.isVisibleTo(p):
        qtbot.mouseClick(insp.advanced_toggle, Qt.LeftButton)
    insp.mode_buttons[FitMode.CONTAIN].click()
    assert not insp.ppi_spin.isVisibleTo(p) and insp.spec().ppi == 180


def test_crop_dialog_price_matches_card(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (1000, 1000))
    seen = []
    page._run_crop_dialog = lambda dlg: seen.append(dlg)
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    text = seen[0]._describe(CropRect(0.0, 0.0, 1.0, 0.766))  # 60 × 46 auto → se cobra 50
    assert "60 × 46 cm" in text and "$11.000" in text


def test_unchanged_crop_keeps_approval(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, (1000, 1000))
    page.controller.approve(0)
    page._run_crop_dialog = lambda dlg: dlg.crop_rect()
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    assert page.controller.items[0].status == ItemStatus.APPROVED
