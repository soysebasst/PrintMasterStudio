import pytest

from printmaster.app_services.job_controller import JobController
from printmaster.app_services.next_step import next_step
from printmaster.domain.models import ItemStatus
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    return JobController(Settings(output_dir=tmp_path / "out"), load_profile())


def test_empty(ctrl):
    assert next_step(ctrl, False, False) == "Arrastra o agrega las imágenes del cliente"


def test_analyzing(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(3000, 4500))])
    assert next_step(ctrl, True, False) == "Analizando imágenes…"


def test_low_quality(ctrl, make_image):
    ctrl.add_paths([make_image("respeto.jpg", size=(236, 420))])
    ctrl.analyze(0)
    assert next_step(ctrl, False, False) == (
        "Mejora «respeto.jpg» con Gemini o apruébala tal cual")


def test_enhancing(ctrl, make_image):
    ctrl.add_paths([make_image("respeto.jpg", size=(236, 420))])
    ctrl.analyze(0)
    assert next_step(ctrl, False, True) == "Mejorando imágenes…"


def test_ready(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(3000, 4500))])
    ctrl.analyze(0)
    assert next_step(ctrl, False, False) == "Revisa la vista previa y pulsa Aprobar todo"


def test_approved(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(3000, 4500))])
    ctrl.analyze(0)
    ctrl.approve(0)
    assert next_step(ctrl, False, False) == "Exporta los PDF"


def test_error_plus_approved(ctrl, make_image, tmp_path):
    bad = tmp_path / "roto.jpg"
    bad.write_bytes(b"x" * 50)
    ctrl.add_paths([make_image("a.jpg", size=(3000, 4500)), bad])
    ctrl.analyze(0)
    ctrl.approve(0)
    assert next_step(ctrl, False, False) == "Exporta los PDF"


def test_all_exported(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(3000, 4500))])
    ctrl.items[0].status = ItemStatus.EXPORTED
    assert next_step(ctrl, False, False) == "Listo. Abre la carpeta de salida"
