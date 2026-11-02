"""Fixtures compartidas: factoría de imágenes sintéticas reproducibles."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def texture_array(size: tuple[int, int], seed: int = 1234) -> np.ndarray:
    """Ruido de valor suavizado (con detalle a varias escalas), RGB uint8."""
    w, h = size
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w, 3), dtype=np.float64)
    for cell, weight in ((64, 0.5), (16, 0.3), (4, 0.2)):
        gh, gw = max(2, h // cell + 2), max(2, w // cell + 2)
        grid = rng.random((gh, gw, 3))
        small = Image.fromarray((grid * 255).astype(np.uint8), "RGB")
        big = np.asarray(small.resize((w, h), Image.BICUBIC), dtype=np.float64) / 255.0
        acc += weight * big
    return np.clip(acc * 255, 0, 255).astype(np.uint8)


def _build(size, mode, pattern, color, seed):
    if pattern == "solid":
        return Image.new(mode, size, color if color is not None else 128)
    arr = texture_array(size, seed)
    img = Image.fromarray(arr, "RGB")
    if mode == "RGB":
        return img
    if mode == "RGBA":
        rgba = img.convert("RGBA")
        alpha = Image.new("L", size, 255)
        rgba.putalpha(alpha)
        return rgba
    return img.convert(mode)


@pytest.fixture
def make_image(tmp_path: Path):
    """make_image(name, size=(w,h), mode="RGB", fmt=None, exif_orientation=None,
    icc=None, pattern="texture", color=None, quality=92, seed=1234, folder=None) -> Path
    """

    def factory(
        name: str,
        size: tuple[int, int] = (400, 300),
        mode: str = "RGB",
        fmt: str | None = None,
        exif_orientation: int | None = None,
        icc: bytes | None = None,
        pattern: str = "texture",
        color=None,
        quality: int = 92,
        seed: int = 1234,
        folder: Path | None = None,
    ) -> Path:
        base = folder if folder is not None else tmp_path
        base.mkdir(parents=True, exist_ok=True)
        path = base / name
        img = _build(size, mode, pattern, color, seed)
        if fmt is None:
            ext = path.suffix.lower()
            fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF",
                   ".tiff": "TIFF", ".webp": "WEBP", ".bmp": "BMP"}[ext]
        kwargs: dict = {}
        if fmt == "JPEG":
            kwargs["quality"] = quality
        if icc is not None:
            kwargs["icc_profile"] = icc
        if exif_orientation is not None:
            exif = Image.Exif()
            exif[0x0112] = exif_orientation
            kwargs["exif"] = exif.tobytes()
        img.save(path, fmt, **kwargs)
        return path

    return factory


@pytest.fixture
def fake_engine_cmd() -> list[str]:
    """Comando del ejecutable falso de Real-ESRGAN."""
    import sys
    return [sys.executable, str(Path(__file__).parent / "fakes" / "fake_realesrgan.py")]
