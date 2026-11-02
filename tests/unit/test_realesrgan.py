import threading
import time

import pytest
from PIL import Image

from printmaster.core.enhance.conservative import upscale_conservative
from printmaster.core.enhance.realesrgan import (
    NO_VULKAN_MESSAGE,
    EnhanceCancelled,
    EnhanceError,
    RealEsrgan,
)


def src_img(tmp_path, size=(20, 10)):
    p = tmp_path / "in.png"
    Image.new("RGB", size, (9, 9, 9)).save(p)
    return p


def test_upscale_x4(fake_engine_cmd, tmp_path):
    out = tmp_path / "out.png"
    RealEsrgan(fake_engine_cmd).upscale_x4(src_img(tmp_path), out, "realesrgan-x4plus")
    assert Image.open(out).size == (80, 40)


def test_failure_raises(fake_engine_cmd, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_FAIL", "1")
    with pytest.raises(EnhanceError) as e:
        RealEsrgan(fake_engine_cmd).upscale_x4(src_img(tmp_path), tmp_path / "o.png", "m")
    assert "vkCreateInstance" in str(e.value)


def test_self_test_no_vulkan(fake_engine_cmd, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_FAIL", "1")
    ok, msg = RealEsrgan(fake_engine_cmd).self_test(tmp_path)
    assert ok is False and msg == NO_VULKAN_MESSAGE


def test_self_test_ok(fake_engine_cmd, tmp_path):
    assert RealEsrgan(fake_engine_cmd).self_test(tmp_path) == (True, "Motor listo")


def test_cancel(fake_engine_cmd, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "5")
    ev = threading.Event()
    threading.Timer(0.3, ev.set).start()
    t0 = time.monotonic()
    with pytest.raises(EnhanceCancelled):
        RealEsrgan(fake_engine_cmd).upscale_x4(src_img(tmp_path), tmp_path / "o.png", "m",
                                               cancel=ev)
    assert time.monotonic() - t0 < 2


def test_conservative():
    out = upscale_conservative(Image.new("RGB", (10, 10)), 4)
    assert out.size == (40, 40)
