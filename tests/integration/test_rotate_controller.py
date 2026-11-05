from datetime import date
from decimal import Decimal as D

import pytest
from pypdf import PdfReader

from printmaster.app_services.job_controller import JobController
from printmaster.domain.models import CropRect, FitMode, PrintSpec
from printmaster.domain.units import mm_to_pt
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    return JobController(Settings(output_dir=tmp_path / "out"), load_profile())


def test_auto_rotates_landscape_on_portrait_sheet(ctrl, make_image, tmp_path):
    ctrl.add_paths([make_image("h.jpg", size=(1500, 1000))])
    ctrl.set_spec(PrintSpec(D(600), D(900)))
    ctrl.set_mode(FitMode.CONTAIN)
    assert ctrl.rotated(0)
    assert ctrl.page_size_for(0) == (600, 900)
    p = ctrl.plan_for(0)
    assert p.rotate and abs(p.dest_rect_pt[2] - p.page_w_pt) < 0.01
    r = ctrl.export([0], tmp_path / "out", today=date(2026, 11, 5))[0]
    box = PdfReader(str(r.output)).pages[0].mediabox
    assert round(float(box.width), 2) == round(mm_to_pt(600), 2)  # sigue en 60 de ancho


def test_no_auto_rotate_in_auto_length(ctrl, make_image):
    ctrl.add_paths([make_image("h.jpg", size=(1500, 1000))])
    assert not ctrl.rotated(0)
    assert ctrl.page_size_for(0) == (600, 400)


def test_manual_rotate_toggle(ctrl, make_image):
    ctrl.add_paths([make_image("h.jpg", size=(1500, 1000))])
    ctrl.set_rotate(0, True)
    assert ctrl.rotated(0) and ctrl.page_size_for(0) == (600, 900)
    ctrl.set_spec(PrintSpec(D(600), D(900)))
    ctrl.set_mode(FitMode.CONTAIN)
    ctrl.set_rotate(0, False)  # forzar sin girar aunque lo automático giraría
    assert not ctrl.rotated(0)


def test_view_region_roundtrip(ctrl, make_image):
    ctrl.add_paths([make_image("h.jpg", size=(1500, 1000))])
    ctrl.set_rotate(0, True)
    ctrl.set_view_region(0, CropRect(0.0, 0.0, 1.0, 0.5))  # mitad de arriba, ya girada
    assert ctrl.view_region(0) == CropRect(0.0, 0.0, 1.0, 0.5)
    assert ctrl.page_size_for(0) == (600, 450)


def test_fixed_size_billed_exactly(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(1000, 1000))])
    ctrl.set_spec(PrintSpec(D(600), D(470)))
    ctrl.set_mode(FitMode.CONTAIN)
    assert ctrl.price_for(0) == 10000  # 60 × 47 fijo: se cobra lo que mide


def test_auto_length_billed_by_steps(ctrl, make_image):
    ctrl.add_paths([make_image("a.jpg", size=(1000, 783))])  # 60 × 47 auto → tramo de 50
    assert ctrl.page_size_for(0) == (600, 470)
    assert ctrl.price_for(0) == 11000
