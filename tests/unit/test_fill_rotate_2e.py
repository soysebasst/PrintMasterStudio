from decimal import Decimal as D
from pathlib import Path

from PIL import Image

from printmaster.core.composer import render_raster
from printmaster.core.layout import page_size_mm, plan
from printmaster.core.pricing import PricingConfig, billable_length_mm, suggest_price
from printmaster.domain.models import CropRect, FitMode, ImageInfo, PrintSpec, rotate_region

SPEC = PrintSpec(D(600), D(900), ppi=200)


def info(w, h, fmt="JPEG"):
    return ImageInfo(Path("x.jpg"), fmt, w, h, "RGB", False, None, 1, 0, "")


def test_auto_length_is_exact_to_the_mm():
    # 1000x1022 → 613,2 mm → lámina de 614 mm, sin franjas de varios cm
    assert page_size_mm(info(1000, 1022), SPEC, FitMode.FIT_LENGTH) == (D(600), D(614))


def test_auto_length_fills_page_without_bands():
    p = plan(info(1000, 1022), SPEC, FitMode.FIT_LENGTH)
    x, y, w, h = p.dest_rect_pt
    assert (x, y) == (0, 0) and abs(w - p.page_w_pt) < 0.01 and abs(h - p.page_h_pt) < 0.01


def test_billable_length_rounds_up_to_step():
    assert billable_length_mm(D(614), 50) == D(650)
    assert billable_length_mm(D(900), 50) == D(900)
    cfg = PricingConfig()
    assert suggest_price(D(600), billable_length_mm(D(614), 50), cfg) == 12000


def test_rotate_region_clockwise():
    r = rotate_region(CropRect(0.0, 0.0, 0.5, 0.25))
    assert (r.x0, r.y0, r.x1, r.y1) == (0.75, 0.0, 1.0, 0.5)
    back = rotate_region(r, inverse=True)
    assert (back.x0, back.y0, back.x1, back.y1) == (0.0, 0.0, 0.5, 0.25)


def test_landscape_image_rotated_fills_portrait_sheet():
    p = plan(info(1500, 1000), SPEC, FitMode.CONTAIN, rotate=True)
    assert p.rotate and not p.passthrough
    assert (p.page_w_mm, p.page_h_mm) == (D(600), D(900))
    assert p.src_box == (0, 0, 1000, 1500)  # en coordenadas de la imagen girada
    x, y, w, h = p.dest_rect_pt
    assert abs(w - p.page_w_pt) < 0.01 and abs(h - p.page_h_pt) < 0.01  # llena la lámina


def test_rotated_auto_length_uses_long_side():
    assert page_size_mm(info(1500, 1000), SPEC, FitMode.FIT_LENGTH, rotate=True) == \
        (D(600), D(900))


def test_render_raster_rotates_clockwise():
    img = Image.new("RGB", (40, 20), (255, 255, 255))
    img.putpixel((0, 0), (255, 0, 0))  # arriba a la izquierda
    p = plan(info(40, 20, "PNG"), PrintSpec(D(100), D(200), ppi=10), FitMode.CONTAIN,
             rotate=True)
    out = render_raster(img, p)
    assert out.width < out.height
    px = out.resize((20, 40)).getpixel((19, 0))
    assert px[0] > 200 and px[1] < 150  # el rojo quedó arriba a la derecha


def test_short_strip_is_not_cropped_across_width():
    p = plan(info(6000, 403), SPEC, FitMode.FIT_LENGTH)
    l, t, r, b = p.src_box
    assert (r - l) == 6000  # no se cortan los lados de una tira corta
