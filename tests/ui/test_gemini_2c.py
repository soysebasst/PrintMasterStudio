import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QDropEvent, QGuiApplication, QImage

from printmaster.domain.models import ItemStatus
from printmaster.printers.profiles import load_profile
from printmaster.ui.pages.job_page import WAIT_TIMEOUT_S, JobPage

pytestmark = pytest.mark.ui


@pytest.fixture
def page(qtbot, settings, tmp_path):
    settings.enhance_enabled = False
    settings.downloads_dir = tmp_path / "descargas"
    settings.downloads_dir.mkdir()
    p = JobPage(settings, load_profile())
    qtbot.addWidget(p)
    p.resize(1366, 740)
    p.show()
    p.messages, p.opened, p.revealed = [], [], []
    p._info = lambda title, text: p.messages.append(text)
    p._open_url = lambda url: p.opened.append(url)
    p._reveal = lambda path: p.revealed.append(path)
    return p


def load(page, qtbot, make_image, tmp_path, specs):
    srcs = [make_image(name, size=size, pattern="solid", color=(200, 120, 60),
                       folder=tmp_path / "in") for name, size in specs]
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(x)) for x in srcs])
    page.queue.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                    Qt.NoModifier))
    qtbot.waitUntil(lambda: len(page.controller.items) == len(specs) and all(
        it.status == ItemStatus.READY for it in page.controller.items), timeout=15000)
    page.queue.list.setCurrentIndex(page.model.index(0))
    return srcs


def gemini_image(w=2304, h=4096) -> QImage:
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(240, 200, 120))
    return img


def test_gemini_copies_image_and_waits_desktop(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    img = QGuiApplication.clipboard().image()
    assert (img.width(), img.height()) == (236, 420)
    assert page.opened == [] and page.revealed == []
    assert page._waiting is not None and page._waiting[0] is page.controller.items[0]
    assert page.quality.wait_label.isVisibleTo(page)
    assert "Imagen copiada" in page.next_label.text()


def test_gemini_caps_long_side(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("big.png", (4000, 1000))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    img = QGuiApplication.clipboard().image()
    assert (img.width(), img.height()) == (3072, 768)


def test_gemini_web_mode_opens_url(page, qtbot, make_image, tmp_path):
    page.settings.gemini_open_mode = "web"
    page.settings.gemini_url = "https://gemini.google.com/gem/abc123"
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    assert page.opened == ["https://gemini.google.com/gem/abc123"]
    assert not page.quality.copy_prompt_btn.isVisibleTo(page)  # hay un Gem


def test_copy_prompt_visible_without_gem(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    assert page.quality.copy_prompt_btn.isVisibleTo(page)
    qtbot.mouseClick(page.quality.copy_prompt_btn, Qt.LeftButton)
    assert QGuiApplication.clipboard().text() == page.settings.gemini_prompt


def test_download_attaches_to_waiting_item(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420)), ("b.jpg", (300, 300))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    page.queue.list.setCurrentIndex(page.model.index(1))  # el usuario cambia de imagen
    Image.new("RGB", (2304, 4096), (240, 200, 120)).save(page.settings.downloads_dir / "g.png")
    page._poll_downloads()
    page._poll_downloads()
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=60000)
    assert page.controller.items[1].enhanced is None
    assert page._waiting is None and not page._watch_timer.isActive()
    qtbot.waitUntil(lambda: "Mejora recibida de Gemini" in page.next_label.text(), timeout=5000)


def test_stop_waiting(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    qtbot.mouseClick(page.quality.stop_wait_btn, Qt.LeftButton)
    assert page._waiting is None and not page._watch_timer.isActive()
    assert not page.quality.wait_label.isVisibleTo(page)


def test_wait_expires(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    page._wait_started -= WAIT_TIMEOUT_S + 1
    page._poll_downloads()
    assert page._waiting is None
    assert "Ya no se espera la descarga de Gemini." in page.next_label.text()


def press_ctrl_v(qtbot, widget):
    widget.window().activateWindow()
    widget.setFocus()
    qtbot.keyClick(widget, Qt.Key_V, Qt.ControlModifier)


def test_ctrl_v_attaches_clipboard_image(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    QGuiApplication.clipboard().setImage(gemini_image())
    press_ctrl_v(qtbot, page.queue.list)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=60000)
    assert page.messages == []


def test_paste_button_attaches(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    QGuiApplication.clipboard().setImage(gemini_image())
    qtbot.mouseClick(page.quality.paste_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=60000)


def test_paste_local_file_url(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    g = tmp_path / "g.png"
    Image.new("RGB", (2304, 4096), (240, 200, 120)).save(g)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(g))])
    QGuiApplication.clipboard().setMimeData(mime)
    qtbot.mouseClick(page.quality.paste_btn, Qt.LeftButton)
    qtbot.waitUntil(lambda: page.controller.items[0].enhanced is not None, timeout=60000)


def test_ctrl_v_with_original_still_copied(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    qtbot.mouseClick(page.quality.gemini_btn, Qt.LeftButton)
    qtbot.mouseClick(page.quality.paste_btn, Qt.LeftButton)
    assert any("todavía tiene la imagen original" in m for m in page.messages)
    assert page.controller.items[0].enhanced is None and page._attaching is None


def test_ctrl_v_empty_clipboard(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    QGuiApplication.clipboard().setText("hola")
    qtbot.mouseClick(page.quality.paste_btn, Qt.LeftButton)
    assert page.messages == ["No hay ninguna imagen en el portapapeles."]


def test_ctrl_v_in_spinbox_is_ignored(page, qtbot, make_image, tmp_path):
    load(page, qtbot, make_image, tmp_path, [("a.jpg", (236, 420))])
    QGuiApplication.clipboard().setImage(gemini_image(64, 64))
    press_ctrl_v(qtbot, page.inspector.width_spin)
    page._paste_from_clipboard()  # aunque el atajo llegue, con foco en un campo no hace nada
    qtbot.wait(200)
    assert page._attaching is None and page.controller.items[0].enhanced is None
    assert page.messages == []
