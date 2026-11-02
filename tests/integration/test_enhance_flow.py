import hashlib
from datetime import date

import pytest
from pypdf import PdfReader

from printmaster.app_services.job_controller import JobController
from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.domain.models import EnhanceChoice, FitMode, ItemStatus
from printmaster.domain.quality import QualityLevel
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def setup(tmp_path, monkeypatch, make_image, fake_engine_cmd):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    log = tmp_path / "log.txt"
    monkeypatch.setenv("FAKE_ESRGAN_LOG", str(log))
    ctrl = JobController(Settings(output_dir=tmp_path / "out"), load_profile())
    src = make_image("respeto.jpg", size=(236, 420))
    ctrl.add_paths([src])
    ctrl.analyze(0)
    enh = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache")
    return ctrl, enh, src, log


def test_needs_two_passes(setup):
    ctrl, enh, src, log = setup
    assert ctrl.items[0].diagnosis.base_level == QualityLevel.MUY_BAJA
    assert ctrl.needs_enhancement(0) == 2


def test_enhance_and_export(setup, tmp_path):
    ctrl, enh, src, log = setup
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    ctrl.enhance(0, enh)
    item = ctrl.items[0]
    assert ctrl.source_info(0).width_px == 3776
    assert item.diagnosis.level in (QualityLevel.ACEPTABLE, QualityLevel.BUENA,
                                    QualityLevel.EXCELENTE)
    assert ctrl.page_size_for(0) == (600, 1100)
    assert ctrl.price_for(0) == 17000
    assert ctrl.needs_enhancement(0) == 0
    assert item.status == ItemStatus.READY
    ctrl.approve(0)
    (r,) = ctrl.export(None, tmp_path / "out", today=date(2026, 11, 2))
    reader = PdfReader(str(r.output))
    xo = reader.pages[0]["/Resources"]["/XObject"]["/Im0"].get_object()
    assert xo["/Width"] >= 3500
    assert abs(float(reader.pages[0].mediabox.height) - 1100 * 72 / 25.4) < 0.01
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before


def test_choice_off_reverts(setup):
    ctrl, enh, src, log = setup
    ctrl.enhance(0, enh)
    ctrl.set_enhance_choice(0, EnhanceChoice.OFF)
    assert ctrl.source_info(0).width_px == 236
    assert ctrl.items[0].diagnosis.base_level == QualityLevel.MUY_BAJA
    assert ctrl.needs_enhancement(0) == 0


def test_format_change_no_rerun(setup):
    ctrl, enh, src, log = setup
    ctrl.enhance(0, enh)
    n = len(log.read_text().splitlines())
    ctrl.set_mode(FitMode.CONTAIN)
    assert len(log.read_text().splitlines()) == n
    assert ctrl.price_for(0) == 15000  # 60×90 manual


def test_disabled_in_settings(setup):
    ctrl, enh, src, log = setup
    ctrl.settings.enhance_enabled = False
    assert ctrl.needs_enhancement(0) == 0
    ctrl.set_enhance_choice(0, EnhanceChoice.ON)
    assert ctrl.needs_enhancement(0) >= 1


def test_enhance_failure_keeps_original(setup, monkeypatch):
    ctrl, enh, src, log = setup
    from printmaster.core.enhance import enhancer as enh_mod

    def boom(*a, **k):
        raise enh_mod.EnhanceError("falló")

    monkeypatch.setattr(enh, "enhance", boom)
    with pytest.raises(enh_mod.EnhanceError):
        ctrl.enhance(0, enh)
    item = ctrl.items[0]
    assert item.enhancing is False and item.enhanced is None
    assert item.status == ItemStatus.READY and "falló" in item.error
    assert ctrl.source_info(0).width_px == 236
