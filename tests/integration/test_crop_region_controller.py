from datetime import date

import pytest
from pypdf import PdfReader

from printmaster.app_services.job_controller import JobController
from printmaster.domain.models import CropRect, ItemStatus
from printmaster.domain.units import mm_to_pt
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    return JobController(Settings(output_dir=tmp_path / "out"), load_profile())


def test_region_changes_length_price_and_pdf(ctrl, make_image, tmp_path):
    ctrl.add_paths([make_image("a.jpg", size=(1000, 1000))])
    assert ctrl.page_size_for(0) == (600, 600)
    ctrl.analyze(0)
    ctrl.approve(0)
    ctrl.set_region(0, CropRect(0.0, 0.0, 1.0, 0.5))
    assert ctrl.items[0].status != ItemStatus.APPROVED  # cambiar el recorte revoca
    assert ctrl.page_size_for(0) == (600, 300)
    assert ctrl.price_for(0) == 10000
    assert ctrl.plan_for(0).src_box == (0, 0, 1000, 500)
    r = ctrl.export([0], tmp_path / "out", today=date(2026, 11, 2))[0]
    box = PdfReader(str(r.output)).pages[0].mediabox
    assert round(float(box.height), 2) == round(mm_to_pt(300), 2)


def test_region_lowers_effective_ppi(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(1000, 1000))])
    ctrl.analyze(0)
    full = ctrl.items[0].diagnosis.effective_ppi
    ctrl.set_region(0, CropRect(0.0, 0.0, 0.5, 0.5))
    assert ctrl.items[0].diagnosis.effective_ppi == pytest.approx(full / 2, rel=0.02)


def test_reset_region(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(1000, 1000))])
    ctrl.set_region(0, CropRect(0.0, 0.0, 1.0, 0.5))
    ctrl.set_region(0, CropRect())
    assert ctrl.items[0].region.is_full and ctrl.page_size_for(0) == (600, 600)


def test_passthrough_region_is_clipped_in_pdf(ctrl, make_image, tmp_path):
    # 1000x1000 recortada a 1000x450 → largo 30 cm (redondeado): sobran bandas que no deben
    # mostrar el resto de la foto
    ctrl.add_paths([make_image("a.jpg", size=(1000, 1000))])
    ctrl.set_region(0, CropRect(0.0, 0.0, 1.0, 0.45))
    plan = ctrl.plan_for(0)
    assert plan.passthrough
    r = ctrl.export([0], tmp_path / "out", today=date(2026, 11, 2))[0]
    content = PdfReader(str(r.output)).pages[0].get_contents().get_data().decode()
    x, y, w, h = plan.dest_rect_pt
    assert " re W n" in content
