"""Prueba con el motor real instalado (se ejecuta a mano: pytest -m gpu)."""

import pytest
from PIL import Image

from printmaster.core.enhance.installer import find_engine

pytestmark = pytest.mark.gpu


def test_real_engine_upscales(tmp_path):
    engine = find_engine()
    if engine is None:
        pytest.skip("Motor Real-ESRGAN no instalado (Configuración › Instalar motor de mejora)")
    ok, msg = engine.self_test(tmp_path)
    assert ok, msg
    src, dst = tmp_path / "in.png", tmp_path / "out.png"
    Image.new("RGB", (64, 64), (200, 50, 50)).save(src)
    engine.upscale_x4(src, dst, "realesrgan-x4plus-anime")
    assert Image.open(dst).size == (256, 256)
