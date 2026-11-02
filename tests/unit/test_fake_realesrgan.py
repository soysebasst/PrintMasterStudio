import subprocess

from PIL import Image


def test_fake_scales_x4(fake_engine_cmd, tmp_path):
    src, dst = tmp_path / "a.png", tmp_path / "b.png"
    Image.new("RGB", (10, 8), (1, 2, 3)).save(src)
    r = subprocess.run(fake_engine_cmd + ["-i", str(src), "-o", str(dst), "-n", "m", "-s", "4"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert Image.open(dst).size == (40, 32)
    assert "fake: m" in r.stderr


def test_fake_fail(fake_engine_cmd, tmp_path, monkeypatch):
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(src)
    monkeypatch.setenv("FAKE_ESRGAN_FAIL", "1")
    r = subprocess.run(fake_engine_cmd + ["-i", str(src), "-o", str(tmp_path / "b.png")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "vkCreateInstance" in r.stderr
