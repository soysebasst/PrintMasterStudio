from pathlib import Path

import pytest
from PIL import Image

from printmaster.core.image_loader import (
    ImageLoadError,
    collect_images,
    load_proxy,
    load_rgb,
    make_thumbnail,
    probe,
)


def test_probe_applies_exif_orientation(make_image):
    p = make_image("rot.jpg", size=(400, 300), exif_orientation=6)
    info = probe(p)
    assert (info.width_px, info.height_px) == (300, 400)
    assert info.exif_orientation == 6
    assert info.format == "JPEG"
    assert len(info.sha256) == 64
    assert info.file_size == p.stat().st_size


def test_load_rgb_applies_exif(make_image):
    p = make_image("rot.jpg", size=(400, 300), exif_orientation=6)
    img, _ = load_rgb(p)
    assert img.size == (300, 400)


def test_unicode_path(make_image, tmp_path):
    p = make_image("Señal Peña ó.jpg", folder=tmp_path / "Diseños")
    assert probe(p).width_px == 400
    img, _ = load_rgb(p)
    assert img.mode == "RGB"


def test_cmyk_jpeg_converted_not_inverted(tmp_path):
    p = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (64, 64), (0, 255, 0, 0)).save(p, "JPEG", quality=95)
    info = probe(p)
    assert info.mode == "CMYK"
    img, icc = load_rgb(p)
    assert img.mode == "RGB"
    r, g, b = img.getpixel((32, 32))
    assert r > 200 and g < 80 and b > 150  # magenta
    assert icc is not None


def test_16bit_tiff(tmp_path):
    p = tmp_path / "deep.tif"
    Image.new("I;16", (50, 40), 40000).save(p, "TIFF")
    img, _ = load_rgb(p)
    assert img.mode in {"L", "RGB"}
    assert img.getpixel((5, 5)) != 0


def test_png_rgba(make_image):
    p = make_image("logo.png", mode="RGBA")
    info = probe(p)
    assert info.has_alpha is True
    img, _ = load_rgb(p)
    assert img.mode == "RGBA"


def test_palette_png_with_transparency(tmp_path):
    p = tmp_path / "pal.png"
    img = Image.new("P", (20, 20), 0)
    img.info["transparency"] = 0
    img.save(p, transparency=0)
    assert probe(p).has_alpha is True
    out, _ = load_rgb(p)
    assert out.mode == "RGBA"


def test_corrupt_file_raises(tmp_path):
    p = tmp_path / "roto.jpg"
    p.write_bytes(b"esto no es una imagen" * 10)
    with pytest.raises(ImageLoadError) as e:
        probe(p)
    assert "roto.jpg" in str(e.value)
    with pytest.raises(ImageLoadError):
        load_rgb(p)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ImageLoadError):
        probe(tmp_path / "no.jpg")


def test_collect_images_recursive_natural(make_image, tmp_path):
    sub = tmp_path / "pedido" / "sub"
    a10 = make_image("a10.png", folder=sub)
    a2 = make_image("a2.JPG", folder=sub, fmt="JPEG")
    (sub / "notas.txt").write_text("x")
    result = collect_images([tmp_path / "pedido", a2])
    assert result == [a2, a10]


def test_thumbnail_and_proxy(make_image):
    p = make_image("big.jpg", size=(3000, 2000))
    thumb = make_thumbnail(p)
    assert max(thumb.size) <= 256
    proxy = load_proxy(p, max_side=1024)
    assert max(proxy.size) <= 1024 and proxy.mode == "RGB"


def test_thumbnail_respects_exif(make_image):
    p = make_image("rot.jpg", size=(400, 300), exif_orientation=6)
    t = make_thumbnail(p)
    assert t.size[1] > t.size[0]
    assert isinstance(p, Path)
