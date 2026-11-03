import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.domain.models import ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import JobPage
from printmaster.ui.pages.settings_page import SettingsPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings, fake_engine_cmd, tmp_path):
    settings.enhance_enabled = True  # aunque quedara activado de antes
    p = JobPage(settings, load_profile(),
                enhancer=Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache"))
    qtbot.addWidget(p)
    p.resize(1366, 740)
    p.show()
    p.messages = []
    p._info = lambda title, text: p.messages.append(text)
    return p


def load(page, qtbot, make_image, tmp_path, size=(236, 420)):
    src = make_image("a.jpg", size=size, folder=tmp_path / "in")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src))])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))
    qtbot.waitUntil(lambda: page.controller.items and
                    page.controller.items[0].status == ItemStatus.READY, timeout=10000)
    page.queue.list.setCurrentIndex(page.model.index(0))


def test_no_automatic_local_enhancement(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path)  # 32 PPI: antes se mejoraba sola
    qtbot.wait(500)
    item = page.controller.items[0]
    assert item.enhanced is None and not item.enhancing and page._enhancing is None
    assert not page.inspector.enhance_combo.isVisibleTo(page)
    assert not page.cancel_enhance_btn.isVisible()


def test_gemini_result_is_not_upscaled_locally(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path)
    g = tmp_path / "g.png"
    Image.new("RGB", (765, 1024), (240, 200, 120)).save(g)
    page._on_external_dropped(g)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=20000)
    assert page.controller.items[0].enhanced.engine == "Gemini (web)"
    assert page.controller.items[0].enhanced_info.width_px == 765


def test_settings_hides_local_engine(qtbot, settings):
    p = SettingsPage(settings)
    qtbot.addWidget(p)
    p.show()
    assert not p.ai_box.isVisibleTo(p)
