"""Pruebas de los hallazgos de la revisión final de la Fase 2A."""

import hashlib
import io
import threading
import time
import zipfile
from datetime import date

import pytest

from printmaster.app_services.job_controller import JobController
from printmaster.core.enhance import installer
from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.realesrgan import RealEsrgan, exe_name
from printmaster.domain.models import ItemStatus
from printmaster.domain.quality import QualityLevel
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


def test_pinned_hash_is_official():
    # SHA-256 del zip oficial v0.2.5.0 (45.474.481 bytes), verificado descargándolo.
    assert installer.ENGINE_SHA256 == (
        "abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d")


def test_install_flat_zip_layout(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:  # el zip oficial no tiene carpeta raíz
        z.writestr(exe_name(), b"x")
        z.writestr("models/realesrgan-x4plus.param", b"m")
    data = buf.getvalue()
    exe = installer.install_engine(tmp_path, "u", hashlib.sha256(data).hexdigest(),
                                   opener=lambda u: io.BytesIO(data))
    assert exe.exists() and installer.find_engine(tmp_path) is not None


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    return JobController(Settings(output_dir=tmp_path / "out"), load_profile())


def test_remove_earlier_item_during_enhance(ctrl, make_image, tmp_path, fake_engine_cmd,
                                            monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "1")
    a = make_image("a.jpg", size=(1200, 1800), seed=1)
    b = make_image("b.jpg", size=(236, 420), seed=2)
    ctrl.add_paths([a, b])
    ctrl.analyze(0)
    ctrl.analyze(1)
    item_b = ctrl.items[1]
    enh = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache")
    errors = []
    t = threading.Thread(target=lambda: _safe(lambda: ctrl.enhance(1, enh), errors))
    t.start()
    time.sleep(0.4)
    ctrl.remove([0])
    t.join(20)
    assert errors == []
    assert ctrl.items[0] is item_b and item_b.enhanced is not None
    assert item_b.diagnosis.base_level != QualityLevel.MUY_BAJA


def test_move_approved_into_index_during_enhance(ctrl, make_image, tmp_path, fake_engine_cmd,
                                                monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "1")
    low = make_image("a_low.jpg", size=(236, 420), seed=2)
    good = make_image("b_good.jpg", size=(3000, 4500), seed=3)
    ctrl.add_paths([low, good])
    ctrl.analyze(0)
    ctrl.analyze(1)
    ctrl.approve(1)
    enh = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache")
    t = threading.Thread(target=lambda: ctrl.enhance(0, enh))
    t.start()
    time.sleep(0.4)
    ctrl.items.reverse()  # el aprobado pasa al índice 0
    t.join(20)
    good_item = next(it for it in ctrl.items if it.path == good)
    assert good_item.status == ItemStatus.APPROVED


def _safe(fn, errors):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        errors.append(exc)


def test_one_too_long_item_does_not_block_batch(ctrl, make_image, tmp_path):
    tall = make_image("alta.png", size=(100, 20000))
    ok = make_image("ok.jpg", size=(554, 554))
    ctrl.add_paths([tall, ok])
    ctrl.analyze(1)
    ctrl.approve(1)
    results = ctrl.export(None, tmp_path / "out", today=date(2026, 11, 2))
    assert [r.ok for r in results] == [True]
    assert ctrl.exportable_indices() == []  # ya exportado
    assert ctrl.price_for(0) is None  # lámina inválida: sin precio
    assert ctrl.total_price() == (1, 12000)


def test_length_and_price_stable_after_enhancement(ctrl, make_image, tmp_path, fake_engine_cmd):
    src = make_image("r.jpg", size=(2400, 4400))
    ctrl.add_paths([src])
    ctrl.analyze(0)
    before = (ctrl.page_size_for(0), ctrl.price_for(0))
    from printmaster.domain.models import EnhanceChoice
    ctrl.set_enhance_choice(0, EnhanceChoice.ON)
    ctrl.enhance(0, Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache"))
    assert ctrl.source_info(0).height_px == 12000  # limitado
    assert (ctrl.page_size_for(0), ctrl.price_for(0)) == before


def test_memory_error_becomes_enhance_error(ctrl, make_image, tmp_path, monkeypatch):
    from printmaster.core.enhance.enhancer import EnhanceError
    src = make_image("r.jpg", size=(236, 420))
    ctrl.add_paths([src])
    ctrl.analyze(0)
    enh = Enhancer(None, tmp_path / "c")
    monkeypatch.setattr(enh, "enhance", lambda *a, **k: (_ for _ in ()).throw(MemoryError()))
    with pytest.raises(EnhanceError):
        ctrl.enhance(0, enh)
    assert "memoria" in ctrl.items[0].error.lower()
    assert ctrl.items[0].enhancing is False
