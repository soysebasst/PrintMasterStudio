import hashlib
from datetime import date

import pytest
from PIL import Image
from pypdf import PdfReader
from tests.conftest import texture_array

from printmaster.app_services.job_controller import JobController
from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.gemini_web import ENGINE_GEMINI, aspect_mismatch
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.core.image_loader import ImageLoadError
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def ctrl(tmp_path, monkeypatch, make_image):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    c = JobController(Settings(output_dir=tmp_path / "out"), load_profile())
    c.add_paths([make_image("respeto.jpg", size=(236, 420))])
    c.analyze(0)
    return c


def gemini_png(tmp_path, size, name="gemini.png"):
    p = tmp_path / "descargas" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(texture_array(size), "RGB").save(p)
    return p


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_attach_gemini_result(ctrl, tmp_path):
    src = gemini_png(tmp_path, (2304, 4096))
    orig = ctrl.items[0].path
    before = (sha(src), sha(orig))
    res = ctrl.attach_external(0, src)
    assert res.aspect_warning is False
    assert res.result.engine == ENGINE_GEMINI
    assert ctrl.source_info(0).width_px == 2304
    assert ctrl.page_size_for(0) == (600, 1068) and ctrl.price_for(0) == 17000
    ctrl.approve(0)
    (r,) = ctrl.export(None, tmp_path / "out", today=date(2026, 11, 2))
    box = PdfReader(str(r.output)).pages[0].mediabox
    assert abs(float(box.height) - 1068 * 72 / 25.4) < 0.01
    assert (sha(src), sha(orig)) == before
    assert src.exists()


def test_low_res_gemini_gets_local_pass(ctrl, tmp_path, fake_engine_cmd):
    src = gemini_png(tmp_path, (236, 420))
    res = ctrl.attach_external(0, src, Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c"))
    assert "+ Real-ESRGAN" in res.result.engine
    assert ctrl.source_info(0).width_px >= 900


def test_aspect_mismatch_fits_without_distortion(ctrl, tmp_path):
    res = ctrl.attach_external(0, gemini_png(tmp_path, (1024, 1024)))
    assert res.aspect_warning is True
    assert ctrl.page_size_for(0) == (600, 1068)
    x, y, w, h = ctrl.plan_for(0).dest_rect_pt
    assert abs(w / h - 1.0) < 0.01


def test_corrupt_drop_keeps_previous(ctrl, tmp_path):
    ctrl.attach_external(0, gemini_png(tmp_path, (2304, 4096)))
    prev = ctrl.items[0].enhanced
    bad = tmp_path / "descargas" / "roto.jpg"
    bad.write_bytes(b"no es imagen" * 20)
    with pytest.raises(ImageLoadError):
        ctrl.attach_external(0, bad)
    assert ctrl.items[0].enhanced == prev


def test_aspect_helper():
    assert aspect_mismatch((236, 420), (2304, 4096)) is False
    assert aspect_mismatch((236, 420), (1024, 1024)) is True


def test_approve_all_includes_gemini_results_even_if_low(ctrl, tmp_path, make_image):
    ctrl.add_paths([make_image("otra.jpg", size=(236, 420), seed=7)])
    ctrl.analyze(1)
    ctrl.attach_external(0, gemini_png(tmp_path, (1152, 2048)))  # sin pase local: «Baja»
    skipped = ctrl.approve_all()
    assert skipped == [1]  # la que no pasó por Gemini sigue pidiendo revisión individual
    assert ctrl.items[0].status.name == "APPROVED"


def test_approve_all_skips_gemini_smaller_than_original(tmp_path, monkeypatch, make_image):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    c = JobController(Settings(output_dir=tmp_path / "out"), load_profile())
    c.add_paths([make_image("big.jpg", size=(1200, 1800))])
    c.analyze(0)
    c.attach_external(0, gemini_png(tmp_path, (500, 750)))
    assert c.approve_all() == [0]
