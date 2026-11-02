from PIL import Image

from printmaster.core.color import edge_color, flatten_alpha, srgb_icc


def test_flatten_transparent_is_white():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    out = flatten_alpha(img)
    assert out.mode == "RGB"
    assert out.getpixel((5, 5)) == (255, 255, 255)


def test_flatten_keeps_other_modes():
    img = Image.new("L", (4, 4), 9)
    assert flatten_alpha(img) is img


def test_edge_color():
    img = Image.new("RGB", (200, 200), (255, 0, 0))
    img.paste((0, 0, 255), (20, 20, 180, 180))
    r, g, b = edge_color(img)
    assert r > 240 and g < 15 and b < 15


def test_srgb_icc_bytes():
    data = srgb_icc()
    assert isinstance(data, bytes) and len(data) > 100
