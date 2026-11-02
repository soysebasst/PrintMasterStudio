from decimal import Decimal as D

import numpy as np
from PIL import Image

from printmaster.core.composer import render_raster
from printmaster.domain.models import Background, BackgroundKind, RenderPlan


def make_plan(src_box, output_px, compose=False):
    return RenderPlan(D(100), D(100), 283.46, 283.46, src_box, (0, 0, 283.46, 283.46),
                      output_px, compose, Background(BackgroundKind.BLUR if compose
                                                     else BackgroundKind.WHITE), 100.0, False)


def test_resize():
    img = Image.new("RGB", (1000, 800), (10, 20, 30))
    out = render_raster(img, make_plan((0, 0, 1000, 800), (500, 400)))
    assert out.size == (500, 400)


def test_crop_without_resize():
    img = Image.new("RGB", (1000, 800))
    out = render_raster(img, make_plan((100, 0, 900, 800), None))
    assert out.size == (800, 800)


def test_compose_page_blur_background():
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 255, (600, 300, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    out = render_raster(img, make_plan((0, 0, 300, 600), (900, 600), compose=True))
    assert out.size == (900, 600)
    fg = np.asarray(img.resize((300, 600), Image.LANCZOS), dtype=np.float64)
    center = np.asarray(out, dtype=np.float64)[:, 300:600]
    assert np.abs(center - fg).mean() < 3


def test_alpha_flattened_by_default():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    out = render_raster(img, make_plan((0, 0, 10, 10), None))
    assert out.mode == "RGB" and out.getpixel((5, 5)) == (255, 255, 255)


def test_keep_alpha():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    out = render_raster(img, make_plan((0, 0, 10, 10), None), keep_alpha=True)
    assert out.mode == "RGBA"
