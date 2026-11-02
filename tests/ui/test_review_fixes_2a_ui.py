from decimal import Decimal as D
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.domain.models import FitMode, ImageInfo, ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import JobPage
from printmaster.ui.widgets.diagnosis_card import DiagnosisCard

pytestmark = pytest.mark.ui


def make_page(qtbot, settings, enhancer):
    p = JobPage(settings, load_profile(), enhancer=enhancer)
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


def test_cover_preview_uses_enhanced_size(qtbot, settings, fake_engine_cmd, tmp_path,
                                          make_image):
    page = make_page(qtbot, settings, Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c"))
    drop(page, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    page.inspector.mode_combo.setCurrentIndex(page.inspector.mode_combo.findData(FitMode.COVER))
    qtbot.waitUntil(lambda: page.canvas.image_item is not None and
                    page.canvas.image_item.sceneBoundingRect().width()
                    >= page.canvas.page_item.rect().width() - 1, timeout=5000)


def test_cancel_sticks_after_param_change(qtbot, settings, fake_engine_cmd, tmp_path,
                                          make_image, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "5")
    page = make_page(qtbot, settings, Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c"))
    drop(page, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhancing, timeout=10000)
    qtbot.mouseClick(page.cancel_enhance_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: page._enhancing is None, timeout=5000)
    page.inspector.ppi_combo.setCurrentIndex(page.inspector.ppi_combo.findData(150))
    qtbot.wait(400)
    assert page._enhancing is None and not page._enhance_queue


def test_remove_enhancing_item_cancels(qtbot, settings, fake_engine_cmd, tmp_path,
                                       make_image, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "5")
    page = make_page(qtbot, settings, Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c"))
    drop(page, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhancing, timeout=10000)
    page.queue.list.setCurrentIndex(page.model.index(0))
    page.queue.remove_selected()
    qtbot.waitUntil(lambda: page._enhancing is None, timeout=3000)


def test_basic_enhancement_not_labeled_ai(qtbot, settings, tmp_path, make_image):
    page = make_page(qtbot, settings, Enhancer(None, tmp_path / "c"))
    drop(page, [make_image("r.jpg", size=(236, 420), folder=tmp_path / "in")])
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    qtbot.waitUntil(lambda: "Mejorada" in page.diagnosis.text(), timeout=5000)
    assert "IA" not in page.diagnosis.text()
    tip = page.model.data(page.model.index(0), Qt.ToolTipRole)
    assert "con IA" not in tip and "básica" in tip
    from printmaster.ui.models.queue_model import EnhancedRole
    assert page.model.data(page.model.index(0), EnhancedRole) == "basic"
    page.controller.items[0].status = ItemStatus.READY
    page._approve_all()
    assert not any("con IA" in m for m in page.messages)


def test_card_shows_error_with_info(qtbot):
    card = DiagnosisCard()
    qtbot.addWidget(card)
    info = ImageInfo(Path("a.jpg"), "JPEG", 236, 420, "RGB", False, None, 1, 1000, "")
    card.show_diagnosis(None, info, error="Memoria insuficiente para mejorar la imagen.",
                        price=17000, page_mm=(D(600), D(1100)))
    assert "Memoria insuficiente" in card.text()
