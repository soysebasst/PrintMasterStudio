import numpy as np
import pytest
from PIL import Image
from tests.conftest import texture_array

from printmaster.core.enhance.enhancer import Enhancer, choose_model, passes_needed
from printmaster.core.enhance.realesrgan import MODEL_ART, MODEL_PHOTO, RealEsrgan


@pytest.mark.parametrize("ppi,expected", [(10, 2), (50, 1), (160, 0), (2, 2), (150, 0)])
def test_passes_needed(ppi, expected):
    assert passes_needed(ppi, 150) == expected


def test_choose_model():
    flat = Image.new("RGB", (100, 100), (255, 255, 255))
    flat.paste((200, 30, 30), (0, 0, 50, 50))
    flat.paste((30, 200, 30), (50, 50, 100, 100))
    assert choose_model(flat) == MODEL_ART
    assert choose_model(Image.fromarray(texture_array((300, 300)), "RGB")) == MODEL_PHOTO


@pytest.fixture
def log(tmp_path, monkeypatch):
    f = tmp_path / "log.txt"
    monkeypatch.setenv("FAKE_ESRGAN_LOG", str(f))
    return f


def lines(f):
    return f.read_text().splitlines() if f.exists() else []


def test_two_passes_and_cache(fake_engine_cmd, tmp_path, make_image, log):
    src = make_image("r.png", size=(236, 420))
    enh = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache")
    r = enh.enhance(src, "abc", 2, MODEL_ART)
    assert Image.open(r.path).size == (3776, 6720)
    assert r.engine == "Real-ESRGAN" and r.passes == 2
    assert len(lines(log)) == 2
    r2 = enh.enhance(src, "abc", 2, MODEL_ART)
    assert r2.path == r.path and len(lines(log)) == 2


def test_max_side_limit(fake_engine_cmd, tmp_path, make_image, log):
    src = make_image("g.png", size=(4000, 3000))
    r = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c").enhance(src, "big", 2, MODEL_PHOTO)
    assert max(Image.open(r.path).size) <= 12000


def test_without_engine_uses_basic(tmp_path, make_image):
    src = make_image("s.png", size=(30, 20))
    r = Enhancer(None, tmp_path / "c").enhance(src, "s", 1, MODEL_PHOTO)
    assert Image.open(r.path).size == (120, 80)
    assert r.engine == "Mejora básica"


def test_engine_failure_falls_back(fake_engine_cmd, tmp_path, make_image, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_FAIL", "1")
    src = make_image("s.png", size=(30, 20))
    r = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c").enhance(src, "s", 1, MODEL_PHOTO)
    assert r.engine == "Mejora básica"
    assert np.asarray(Image.open(r.path)).shape[:2] == (80, 120)


def test_progress_called(fake_engine_cmd, tmp_path, make_image):
    calls = []
    src = make_image("s.png", size=(30, 20))
    Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c").enhance(
        src, "p", 2, MODEL_PHOTO, progress=lambda k, n: calls.append((k, n)))
    assert calls == [(1, 2), (2, 2)]
