import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QPushButton, QStackedWidget

from printmaster.infra.settings import load_settings
from printmaster.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


@pytest.fixture
def win(qtbot, settings):
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    return w


def nav(win) -> QListWidget:
    return win.findChild(QListWidget, "nav")


def stack(win) -> QStackedWidget:
    return win.findChild(QStackedWidget, "pages")


def test_sidebar_entries(win):
    n = nav(win)
    assert [n.item(i).text() for i in range(n.count())] == [
        "Inicio", "Nuevo trabajo", "Configuración"]


def test_sidebar_switches_page(win, qtbot):
    nav(win).setCurrentRow(2)
    assert stack(win).currentIndex() == 2


def test_home_new_job_button(win, qtbot):
    btn = win.findChild(QPushButton, "home_new_job")
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert stack(win).currentIndex() == 1
    assert nav(win).currentRow() == 1


def test_settings_save_prefix(win, qtbot):
    page = win.settings_page
    page.prefix_edit.setText("Pedido")
    qtbot.mouseClick(page.save_btn, Qt.LeftButton)
    assert load_settings().naming_prefix == "Pedido"


def test_delete_favorite(win, qtbot):
    page = win.settings_page
    page.favorites_list.setCurrentRow(0)
    qtbot.mouseClick(page.delete_favorite_btn, Qt.LeftButton)
    qtbot.mouseClick(page.save_btn, Qt.LeftButton)
    assert len(load_settings().favorites) == 5
