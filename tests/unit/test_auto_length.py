from decimal import Decimal as D
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from printmaster.core.layout import auto_length_mm, page_size_mm, plan
from printmaster.domain.models import FitMode, ImageInfo, Orientation, PrintSpec


def info(w, h):
    return ImageInfo(Path("x.jpg"), "JPEG", w, h, "RGB", False, None, 1, 0, "")


@pytest.mark.parametrize("w,h,expected", [
    (554, 554, 600), (236, 420, 1100), (4000, 3000, 450), (3000, 4500, 900),
    (1000, 3000, 1800), (3000, 1000, 200), (3000, 100, 50),
])
def test_auto_length_examples(w, h, expected):
    assert auto_length_mm(D(600), w, h) == D(expected)


@given(st.integers(1, 20000), st.integers(1, 20000))
def test_auto_length_properties(w, h):
    exact = D(600) * h / w
    got = auto_length_mm(D(600), w, h)
    assert got >= exact - D("0.000001")
    assert got < exact + 50 or got == 50
    assert got % 50 == 0


def test_fit_length_plan():
    p = plan(info(236, 420), PrintSpec(D(600), D(900)), FitMode.FIT_LENGTH)
    assert (p.page_w_mm, p.page_h_mm) == (D(600), D(1068))  # 2E: largo justo al mm
    x, y, w, h = p.dest_rect_pt
    assert abs(w - p.page_w_pt) < 1e-6 and abs(x) < 1e-6
    assert abs(y) < 1e-6 and abs(h - p.page_h_pt) < 1e-6  # sin franjas


def test_fit_length_landscape_not_rotated():
    p = plan(info(4000, 3000), PrintSpec(D(600), D(900), orientation=Orientation.AS_ENTERED),
             FitMode.FIT_LENGTH)
    assert (p.page_w_mm, p.page_h_mm) == (D(600), D(450))


def test_as_entered_keeps_spec():
    s = PrintSpec(D(600), D(900), orientation=Orientation.AS_ENTERED).resolved_for(4000, 3000)
    assert (s.width_mm, s.height_mm) == (D(600), D(900))


def test_page_size_mm():
    assert page_size_mm(info(554, 554), PrintSpec(D(600), D(900)), FitMode.FIT_LENGTH) == (
        D(600), D(600))
    spec = PrintSpec(D(600), D(900), orientation=Orientation.AS_ENTERED)
    assert page_size_mm(info(4000, 3000), spec, FitMode.CONTAIN) == (D(600), D(900))
