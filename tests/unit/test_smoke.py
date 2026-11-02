from PIL import Image

import printmaster


def test_version():
    assert printmaster.__version__ == "0.1.0"


def test_make_image_creates_readable_jpeg(make_image):
    path = make_image("a.jpg", size=(40, 30))
    with Image.open(path) as img:
        assert img.size == (40, 30)
        assert img.format == "JPEG"
