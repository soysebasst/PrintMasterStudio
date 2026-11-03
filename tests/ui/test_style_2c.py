from importlib import resources

import pytest
from PySide6.QtCore import Qt

from printmaster.ui.icons import ICON_NAMES, icon
from printmaster.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


def test_icons_exist_and_load(qtbot):
    folder = resources.files("printmaster.ui").joinpath("assets/icons")
    for name in ICON_NAMES:
        assert folder.joinpath(f"{name}.svg").is_file(), name
        assert not icon(name).isNull(), name
    assert len(ICON_NAMES) == 13


def test_nav_icons_and_brand(qtbot, settings):
    win = MainWindow(settings)
    qtbot.addWidget(win)
    for i in range(win.nav.count()):
        assert not win.nav.item(i).icon().isNull()
    assert "PrintMaster" in win.brand_label.text()


def test_qss_accent():
    qss = resources.files("printmaster.ui").joinpath("theme.qss").read_text(encoding="utf-8")
    assert "#7c5cff" in qss and "#15131c" in qss


def test_home_favorites_as_buttons(qtbot, settings):
    win = MainWindow(settings)
    qtbot.addWidget(win)
    home = win.home_page
    assert len(home.favorite_buttons) == len(settings.favorites)
    with qtbot.waitSignal(home.favorite_chosen) as blocker:
        qtbot.mouseClick(home.favorite_buttons[1], Qt.LeftButton)
    assert blocker.args[0].name == settings.favorites[1].name
