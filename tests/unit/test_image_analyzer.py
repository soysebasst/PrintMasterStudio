import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter
from tests.conftest import texture_array

from printmaster.core.image_analyzer import (
    analyze,
    estimate_jpeg_quality,
    estimate_noise,
    measure_blockiness,
    measure_sharpness,
)
from printmaster.domain.models import ImageInfo
from printmaster.domain.quality import QualityLevel


def texture(size=(1024, 768)):
    return Image.fromarray(texture_array(size), "RGB")


def gray(img):
    return np.asarray(img.convert("L"))


def blurred(sigma):
    img = texture()
    return img if sigma == 0 else img.filter(ImageFilter.GaussianBlur(sigma))


def info_for(fmt="PNG"):
    return ImageInfo(Path("x"), fmt, 1024, 768, "RGB", False, None, 1, 0, "")


def test_sharpness_decreases_with_blur():
    values = [measure_sharpness(gray(blurred(s))) for s in (0, 1, 2, 4)]
    assert values == sorted(values, reverse=True)
    assert len(set(values)) == 4


def test_blur_warning():
    d_blur = analyze(info_for(), blurred(4), 300)
    d_sharp = analyze(info_for(), blurred(0), 300)
    assert "Posible desenfoque." in d_blur.warnings
    assert "Posible desenfoque." not in d_sharp.warnings


def test_noise_estimate():
    rng = np.random.default_rng(0)
    arr = np.clip(128 + rng.normal(0, 10, (512, 512)), 0, 255)
    sigma = estimate_noise(arr.astype(np.uint8))
    assert 8 <= sigma <= 12


def jpeg_at(q):
    buf = io.BytesIO()
    texture().save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf)


def test_blockiness_and_quality_low():
    img = jpeg_at(20)
    assert measure_blockiness(gray(img)) > 1.5
    assert 15 <= estimate_jpeg_quality(img) <= 25


def test_quality_high():
    img = jpeg_at(95)
    assert 90 <= estimate_jpeg_quality(img) <= 100
    assert measure_blockiness(gray(img)) < 1.5


def test_quality_none_for_png():
    assert estimate_jpeg_quality(texture()) is None


def test_very_low_ppi():
    d = analyze(info_for(), texture(), 60)
    assert d.level == QualityLevel.MUY_BAJA
    assert "Pocos píxeles para este tamaño: 60 PPI efectivos." in d.warnings
    assert d.recommendation == "Se recomienda ampliar (Fase 3) o reducir el tamaño de impresión."


def test_excellent_sharp():
    d = analyze(info_for(), texture(), 300)
    assert d.level == QualityLevel.EXCELENTE
    assert d.recommendation == "Conservar la imagen original."
    assert d.warnings == ()


def test_blur_downgrades_once():
    d = analyze(info_for(), blurred(4), 300)
    assert d.base_level == QualityLevel.EXCELENTE
    assert d.level == QualityLevel.BUENA
    assert d.recommendation == "Revisar la vista previa antes de aprobar."


@pytest.mark.parametrize("q", [20])
def test_jpeg_artifacts_warning(q):
    d = analyze(info_for("JPEG"), jpeg_at(q), 300)
    assert "Artefactos de compresión JPEG." in d.warnings
    assert d.jpeg_quality is not None
