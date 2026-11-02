from datetime import date

import pytest
from pypdf import PdfReader

from printmaster.app_services.job_controller import JobController
from printmaster.domain.models import FitMode
from printmaster.domain.units import mm_to_pt
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    return JobController(Settings(output_dir=tmp_path / "out"), load_profile())


def test_defaults(ctrl):
    assert ctrl.mode == FitMode.FIT_LENGTH
    assert ctrl.spec.width_mm == 600


def test_price_per_item_and_total(ctrl, make_image, tmp_path):
    a = make_image("a.jpg", size=(554, 554))
    b = make_image("b.jpg", size=(236, 420))
    ctrl.add_paths([a, b])
    assert ctrl.price_for(0) == 12000 and ctrl.price_for(1) == 17000
    assert ctrl.total_price() == (2, 29000)
    assert ctrl.page_size_for(1) == (600, 1100)


def test_export_fit_length_sizes(ctrl, make_image, tmp_path):
    ctrl.add_paths([make_image("a.jpg", size=(554, 554)), make_image("b.jpg", size=(236, 420))])
    results = ctrl.export([0, 1], tmp_path / "out", today=date(2026, 11, 2))
    sizes = []
    for r in results:
        box = PdfReader(str(r.output)).pages[0].mediabox
        sizes.append((round(float(box.width), 2), round(float(box.height), 2)))
    assert sizes == [(round(mm_to_pt(600), 2), round(mm_to_pt(600), 2)),
                     (round(mm_to_pt(600), 2), round(mm_to_pt(1100), 2))]


def test_very_tall_image_too_long(ctrl, make_image):
    ctrl.add_paths([make_image("alta.png", size=(100, 20000))])
    assert "too_long" in [x.code for x in ctrl.issues(0)]


def test_panoramic(ctrl, make_image):
    ctrl.add_paths([make_image("pano.jpg", size=(3000, 100))])
    assert ctrl.page_size_for(0) == (600, 50)
    assert ctrl.price_for(0) == 10000


def test_total_skips_errors(ctrl, make_image, tmp_path):
    bad = tmp_path / "roto.jpg"
    bad.write_bytes(b"x" * 100)
    ctrl.add_paths([make_image("a.jpg", size=(554, 554)), bad])
    assert ctrl.total_price() == (1, 12000)
