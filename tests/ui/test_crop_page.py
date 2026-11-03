import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.domain.models import CropRect, ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings):
    settings.enhance_enabled = False
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1366, 740)
    p.show()
    p.messages = []
    p._info = lambda title, text: p.messages.append(text)
    return p


def load(page, qtbot, make_image, tmp_path, size=(1000, 1000)):
    src = make_image("a.jpg", size=size, folder=tmp_path / "in")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))
    qtbot.waitUntil(lambda: page.controller.items and
                    page.controller.items[0].status == ItemStatus.READY, timeout=10000)
    page.queue.list.setCurrentIndex(page.model.index(0))
    qtbot.waitUntil(lambda: page.canvas.image_item is not None, timeout=5000)


def test_crop_button_disabled_without_images(page):
    assert not page.crop_btn.isEnabled() and not page.crop_btn.icon().isNull()


def test_apply_crop_updates_size_price_and_preview(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path)
    full_h = page.canvas.image_item.pixmap().height()
    page._run_crop_dialog = lambda dlg: CropRect(0.0, 0.0, 1.0, 0.5)
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    assert page.controller.page_size_for(0) == (600, 300)
    assert "$10.000" in page.total_label.text()
    qtbot.waitUntil(lambda: page.canvas.image_item is not None and
                    abs(page.canvas.image_item.pixmap().height() - full_h / 2) <= 2, timeout=5000)
    assert "Recortada" in page.info_label.text()


def test_cancel_crop_changes_nothing(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path)
    page._run_crop_dialog = lambda dlg: None
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    assert page.controller.items[0].region.is_full


def test_dialog_has_presets_and_live_price(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path)
    seen = []
    page._run_crop_dialog = lambda dlg: seen.append(dlg)
    qtbot.mouseClick(page.crop_btn, Qt.LeftButton)
    dlg = seen[0]
    names = list(dlg.preset_buttons)
    assert names[:2] == ["Libre", "Original"]
    assert any(n.startswith("60 × 90") for n in names)
    text = dlg._describe(CropRect(0.0, 0.0, 1.0, 0.5))
    assert "60 × 30 cm" in text and "$10.000" in text and "PPI" in text
