from decimal import Decimal as D
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from printmaster.core.layout import full_image_rect_pt, plan
from printmaster.domain.models import (
    Background,
    BackgroundKind,
    CropOffset,
    FitMode,
    ImageInfo,
    PrintSpec,
)
from printmaster.domain.units import mm_to_pt, mm_to_px


def info(w, h, fmt="JPEG", mode="RGB", orient=1):
    return ImageInfo(Path("x.jpg"), fmt, w, h, mode, False, None, orient, 0, "")


SPEC = PrintSpec(D(600), D(900), ppi=200)


def test_contain_landscape_has_side_bands():
    p = plan(info(4000, 3000), SPEC, FitMode.CONTAIN)
    assert (p.page_w_mm, p.page_h_mm) == (D(900), D(600))
    x, y, w, h = p.dest_rect_pt
    assert abs(h - p.page_h_pt) < 1e-6
    assert abs(w / h - 4 / 3) < 0.001
    assert abs(x - (p.page_w_pt - w) / 2) < 1e-6
    assert p.src_box == (0, 0, 4000, 3000)


def test_cover_fills_page_with_page_aspect():
    p = plan(info(4000, 3000), SPEC, FitMode.COVER)
    assert p.dest_rect_pt == (0.0, 0.0, p.page_w_pt, p.page_h_pt)
    l, t, r, b = p.src_box
    assert abs((r - l) / (b - t) - 1.5) < 2 / (b - t)


def test_cover_crop_offsets():
    top = plan(info(4000, 3000), SPEC, FitMode.COVER, crop=CropOffset(0, 0)).src_box
    bottom = plan(info(4000, 3000), SPEC, FitMode.COVER, crop=CropOffset(1, 1)).src_box
    assert top[1] == 0
    assert bottom[3] == 3000


def test_low_res_passthrough():
    p = plan(info(1000, 1500), SPEC, FitMode.CONTAIN)
    assert abs(p.effective_ppi - 42.33) < 0.1
    assert p.output_px is None
    assert p.passthrough is True


def test_high_res_downsampled():
    p = plan(info(12000, 8000), PrintSpec(D(600), D(400), ppi=200), FitMode.CONTAIN)
    assert p.output_px is not None
    assert abs(p.output_px[0] - 4724) <= 1 and abs(p.output_px[1] - 3150) <= 1
    assert p.passthrough is False


def test_exif_rotated_disables_passthrough():
    assert plan(info(1000, 1500, orient=6), SPEC, FitMode.CONTAIN).passthrough is False


def test_png_not_passthrough():
    assert plan(info(1000, 1500, fmt="PNG"), SPEC, FitMode.CONTAIN).passthrough is False


def test_fill_blur_composes_page():
    p = plan(info(1000, 1500), SPEC, FitMode.FILL, Background(BackgroundKind.BLUR))
    assert p.compose_page is True
    assert p.dest_rect_pt == (0.0, 0.0, p.page_w_pt, p.page_h_pt)
    ppi = min(200, p.effective_ppi)
    assert p.output_px == (
        mm_to_px(p.page_w_mm, round(ppi)), mm_to_px(p.page_h_mm, round(ppi))
    )
    assert p.passthrough is False


def test_fill_color_keeps_passthrough():
    p = plan(info(1000, 1500), SPEC, FitMode.FILL, Background(BackgroundKind.COLOR, (10, 20, 30)))
    assert p.passthrough is True
    assert p.background.color == (10, 20, 30)


def test_contain_forces_white():
    p = plan(info(1000, 1500), SPEC, FitMode.CONTAIN, Background(BackgroundKind.COLOR, (1, 2, 3)))
    assert p.background == Background()


def test_unresolved_edge_color_rejected():
    with pytest.raises(ValueError):
        plan(info(1000, 1500), SPEC, FitMode.FILL, Background(BackgroundKind.EDGE_COLOR))


def test_page_points():
    p = plan(info(3000, 4500), SPEC, FitMode.CONTAIN)
    assert abs(p.page_w_pt - mm_to_pt(D(600))) < 1e-9


def test_full_image_rect_contains_dest():
    p = plan(info(4000, 3000), PrintSpec(D(500), D(500)), FitMode.COVER)
    fx, fy, fw, fh = full_image_rect_pt(p, 4000, 3000)
    x, y, w, h = p.dest_rect_pt
    assert fx <= x + 1e-6 and fy <= y + 1e-6
    assert fx + fw >= x + w - 1e-6 and fy + fh >= y + h - 1e-6
    assert fw > p.page_w_pt


@settings(max_examples=300, deadline=None)
@given(
    st.integers(1, 20000), st.integers(1, 20000),
    st.integers(10, 3000), st.integers(10, 3000),
    st.sampled_from(list(FitMode)),
    st.floats(0, 1), st.floats(0, 1),
)
def test_properties(w, h, pw, ph, mode, cx, cy):
    p = plan(info(w, h), PrintSpec(D(pw), D(ph)), mode, crop=CropOffset(cx, cy))
    x, y, dw, dh = p.dest_rect_pt
    eps = 1e-6
    assert x >= -eps and y >= -eps
    assert x + dw <= p.page_w_pt + eps and y + dh <= p.page_h_pt + eps
    l, t, r, b = p.src_box
    assert 0 <= l < r <= w and 0 <= t < b <= h
    fills = abs(dw - p.page_w_pt) < eps and abs(dh - p.page_h_pt) < eps
    if mode == FitMode.COVER or (mode == FitMode.FIT_LENGTH and fills):  # 2E: llena la lámina
        target = p.page_w_pt / p.page_h_pt
        sw, sh = r - l, b - t
        # proporción conservada a ±1 px
        assert abs(sw - target * sh) <= 1 + target or abs(sh - sw / target) <= 1 + 1 / target
    else:
        assert abs(dw / dh - w / h) <= max(w / h, h / w) * 1e-6 + 1e-9
