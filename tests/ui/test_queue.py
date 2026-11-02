import pytest
from PySide6.QtCore import QMimeData, QModelIndex, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from printmaster.app_services.job_controller import JobController
from printmaster.printers.profiles import load_profile
from printmaster.ui.models.queue_model import LOADING, QueueModel
from printmaster.ui.widgets.queue_view import QueueView

pytestmark = pytest.mark.ui


@pytest.fixture
def setup(qtbot, settings, make_image, tmp_path):
    ctrl = JobController(settings, load_profile())
    model = QueueModel(ctrl)
    view = QueueView(model)
    qtbot.addWidget(view)
    view.show()
    files = [make_image(f"f{i}.jpg", seed=i, folder=tmp_path / "in") for i in range(3)]
    txt = tmp_path / "in" / "nota.txt"
    txt.write_text("x")
    return ctrl, model, view, files + [txt]


def drop(view, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    ev = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    view.dropEvent(ev)


def test_drop_files(setup, qtbot):
    ctrl, model, view, paths = setup
    drop(view, paths)
    assert model.rowCount() == 3
    qtbot.waitUntil(lambda: all(
        model.data(model.index(r), Qt.DecorationRole) is not LOADING for r in range(3)),
        timeout=5000)


def test_tooltip(setup):
    ctrl, model, view, paths = setup
    drop(view, paths)
    tip = model.data(model.index(0), Qt.ToolTipRole)
    assert "px" in tip and "MB" in tip


def test_delete_key(setup, qtbot):
    ctrl, model, view, paths = setup
    drop(view, paths)
    view.list.setCurrentIndex(model.index(1))
    view.list.setFocus()
    qtbot.keyClick(view.list, Qt.Key_Delete)
    assert model.rowCount() == 2
    assert [it.path.name for it in ctrl.items] == ["f0.jpg", "f2.jpg"]


def test_move_rows(setup):
    ctrl, model, view, paths = setup
    drop(view, paths)
    assert model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 3)
    assert [it.path.name for it in ctrl.items] == ["f1.jpg", "f2.jpg", "f0.jpg"]


def test_move_up_down(setup, qtbot):
    ctrl, model, view, paths = setup
    drop(view, paths)
    view.list.setCurrentIndex(model.index(2))
    view.up_action.trigger()
    assert [it.path.name for it in ctrl.items] == ["f0.jpg", "f2.jpg", "f1.jpg"]
    assert view.list.currentIndex().row() == 1
    view.down_action.trigger()
    assert [it.path.name for it in ctrl.items] == ["f0.jpg", "f1.jpg", "f2.jpg"]


def test_context_menu_actions(setup):
    ctrl, model, view, paths = setup
    assert [a.text() for a in view.context_menu.actions()] == [
        "Quitar", "Subir", "Bajar", "Abrir carpeta"]


def test_roles(setup, make_image, tmp_path):
    from printmaster.ui.models.queue_model import SizePriceRole, StatusTextRole
    ctrl, model, view, paths = setup
    low = make_image("baja.jpg", size=(236, 420), folder=tmp_path / "x")
    bad = tmp_path / "x" / "roto.jpg"
    bad.write_bytes(b"x" * 50)
    view.add_paths([low, bad])
    ctrl.analyze(0)
    assert model.data(model.index(0), StatusTextRole) == "Mejorar"
    assert model.data(model.index(1), StatusTextRole) == "Error"
    assert "$" in model.data(model.index(0), SizePriceRole)
    ctrl.approve(0)
    assert model.data(model.index(0), StatusTextRole) == "Aprobada"


def test_icon_mode(setup):
    from PySide6.QtWidgets import QListView
    ctrl, model, view, paths = setup
    assert view.list.viewMode() == QListView.IconMode


def test_current_changed_signal(setup, qtbot):
    ctrl, model, view, paths = setup
    drop(view, paths)
    with qtbot.waitSignal(view.current_changed) as blocker:
        view.list.setCurrentIndex(model.index(2))
    assert blocker.args == [2]


def test_drop_from_explorer_onto_list(setup):
    ctrl, model, view, paths = setup
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    ev = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    view.list.dropEvent(ev)
    assert model.rowCount() == 3
