import pytest
from PySide6.QtWidgets import QPushButton, QToolButton

from printmaster.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


def _connected(btn) -> bool:
    meta = btn.metaObject()
    for sig in ("clicked(bool)", "clicked()"):
        idx = meta.indexOfSignal(sig)
        if idx >= 0 and btn.isSignalConnected(meta.method(idx)):
            return True
    return False


def test_every_button_does_something(qtbot, settings):
    win = MainWindow(settings)
    qtbot.addWidget(win)
    win.show()
    buttons = []
    for i in range(win.pages.count()):
        win.nav.setCurrentRow(i)
        page = win.pages.widget(i)
        buttons += page.findChildren(QPushButton) + page.findChildren(QToolButton)
    real = [b for b in buttons if b.text().strip() and type(b).__name__ in (
        "QPushButton", "QToolButton")]
    assert len(real) >= 15
    dead = [b.text() for b in real if not _connected(b)]
    assert dead == []
