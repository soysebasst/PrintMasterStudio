from decimal import Decimal as D
from pathlib import Path

import pytest

from printmaster.core.layout import full_image_rect_pt, page_size_mm, plan
from printmaster.domain.models import CropRect, FitMode, ImageInfo, PrintSpec

SPEC = PrintSpec(D(600), D(900), ppi=200)


def info(w, h, fmt="JPEG"):
    return ImageInfo(Path("x.jpg"), fmt, w, h, "RGB", False, None, 1, 0, "")


def test_croprect_defaults_and_clamps():
    assert CropRect().is_full
    r = CropRect(-0.2, 0.1, 1.5, 0.6)
    assert (r.x0, r.y0, r.x1, r.y1) == (0.0, 0.1, 1.0, 0.6) and not r.is_full
    with pytest.raises(ValueError):
        CropRect(0.5, 0.5, 0.5, 0.9)  # sin ancho


def test_box_in_pixels():
    assert CropRect(0.25, 0.5, 0.75, 1.0).box(400, 200) == (100, 100, 300, 200)


def test_free_crop_sets_auto_length():
    # 1000x1000 recortada a la mitad superior → 1000x500 → 60 × 30 cm
    r = CropRect(0.0, 0.0, 1.0, 0.5)
    assert page_size_mm(info(1000, 1000), SPEC, FitMode.FIT_LENGTH, region=r) == (D(600), D(300))
    p = plan(info(1000, 1000), SPEC, FitMode.FIT_LENGTH, region=r)
    assert p.src_box == (0, 0, 1000, 500)
    assert p.page_h_mm == D(300)


def test_region_uses_original_aspect_on_enhanced_source():
    # aspecto del original 1000x1000; la fuente mejorada 4000x4000: mismo recorte relativo
    r = CropRect(0.0, 0.25, 1.0, 0.75)
    p = plan(info(4000, 4000), SPEC, FitMode.FIT_LENGTH, region=r, aspect_px=(1000, 1000))
    assert p.page_h_mm == D(300) and p.src_box == (0, 1000, 4000, 3000)


def test_region_with_contain_and_cover():
    r = CropRect(0.5, 0.0, 1.0, 1.0)  # mitad derecha de 2000x1000 → 1000x1000
    p = plan(info(2000, 1000), SPEC, FitMode.CONTAIN, region=r)
    assert p.src_box == (1000, 0, 2000, 1000)
    pc = plan(info(2000, 1000), SPEC, FitMode.COVER, region=r)
    l, t, rr, b = pc.src_box
    assert l >= 1000 and rr <= 2000 and t >= 0 and b <= 1000


def test_full_rect_for_passthrough_with_region():
    r = CropRect(0.0, 0.0, 0.5, 1.0)
    p = plan(info(1000, 1000), SPEC, FitMode.FIT_LENGTH, region=r)
    assert p.passthrough  # JPEG recortado: se dibuja entero y se recorta en el PDF
    x, y, w, h = full_image_rect_pt(p, 1000, 1000)
    assert w == pytest.approx(2 * p.dest_rect_pt[2])
