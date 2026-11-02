"""Diagnóstico de calidad de imagen.

Las métricas se calculan sobre una copia reducida (proxy). El nivel de calidad parte del
PPI efectivo en el tamaño físico elegido; nunca se califica una imagen como de alta
calidad solo por su cantidad de píxeles: los detectores de desenfoque, ruido y bloques
JPEG pueden bajarla un nivel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from printmaster.domain.models import ImageInfo
from printmaster.domain.quality import (
    DEFAULT_THRESHOLDS,
    QualityLevel,
    QualityThresholds,
    classify,
    downgrade,
)

# Calibrado con la textura sintética de las pruebas (σ=2 → 3.78, σ=4 → 2.58).
# Valor conservador: solo marca imágenes muy suaves. Recalibrar con fotos reales (Fase 3).
BLUR_THRESHOLD = 3.2
NOISE_THRESHOLD = 8.0
BLOCK_THRESHOLD = 1.5
# Si el proxy fue reducido, la cuadrícula 8×8 ya no está alineada: se usa la calidad JPEG
# estimada (leída de las tablas del archivo original) como indicador de artefactos.
LOW_JPEG_QUALITY = 30
ANALYSIS_SIDE = 1024

# Tabla estándar de luminancia JPEG (Anexo K, ITU-T T.81).
_STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
], dtype=np.float64)

_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)

MSG_BLUR = "Posible desenfoque."
MSG_NOISE = "Ruido visible."
MSG_BLOCKS = "Artefactos de compresión JPEG."
REC_KEEP = "Conservar la imagen original."
REC_UPSCALE = "Se recomienda ampliar (Fase 3) o reducir el tamaño de impresión."
REC_REVIEW = "Revisar la vista previa antes de aprobar."


@dataclass(frozen=True)
class Diagnosis:
    effective_ppi: float
    base_level: QualityLevel
    level: QualityLevel
    sharpness: float
    noise_sigma: float
    blockiness: float
    jpeg_quality: int | None
    warnings: tuple[str, ...]
    recommendation: str


def _resize_long(gray: np.ndarray, side: int = ANALYSIS_SIDE) -> np.ndarray:
    h, w = gray.shape[:2]
    scale = side / max(h, w)
    if abs(scale - 1) < 1e-9:
        return gray
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))),
                      interpolation=interp)


def measure_sharpness(gray: np.ndarray) -> float:
    g = _resize_long(np.asarray(gray, dtype=np.uint8))
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def estimate_noise(gray: np.ndarray) -> float:
    """Desviación estándar del ruido (Immerkær, 1996)."""
    g = np.asarray(gray, dtype=np.float64)
    h, w = g.shape[:2]
    if h < 3 or w < 3:
        return 0.0
    conv = cv2.filter2D(g, cv2.CV_64F, _IMMERKAER)[1:-1, 1:-1]
    return float(math.sqrt(math.pi / 2) * np.abs(conv).sum() / (6 * (w - 2) * (h - 2)))


def measure_blockiness(gray: np.ndarray) -> float:
    """Relación entre la diferencia horizontal en fronteras de bloque 8×8 y el resto."""
    g = np.asarray(gray, dtype=np.float64)
    if g.shape[1] < 17:
        return 1.0
    diff = np.abs(np.diff(g, axis=1))  # diff[:, j] = |g[:, j+1] - g[:, j]|
    cols = np.arange(diff.shape[1])
    boundary = (cols % 8) == 7
    inner = diff[:, ~boundary].mean()
    if inner < 1e-9:
        return 1.0
    return float(diff[:, boundary].mean() / inner)


def _table_for_quality(q: int) -> np.ndarray:
    scale = 5000 / q if q < 50 else 200 - 2 * q
    return np.clip(np.floor((_STD_LUMA * scale + 50) / 100), 1, 255)


def estimate_jpeg_quality(img: Image.Image) -> int | None:
    tables = getattr(img, "quantization", None)
    if not tables or 0 not in tables:
        return None
    target = float(np.sum(tables[0]))
    best = min(range(1, 101), key=lambda q: abs(_table_for_quality(q).sum() - target))
    return best


def _jpeg_quality_for(info: ImageInfo, proxy: Image.Image) -> int | None:
    q = estimate_jpeg_quality(proxy)
    if q is not None or info.format != "JPEG":
        return q
    try:
        with Image.open(info.path) as original:  # solo cabeceras: no decodifica píxeles
            return estimate_jpeg_quality(original)
    except (OSError, ValueError):
        return None


def rerate(
    diag: Diagnosis,
    effective_ppi: float,
    thresholds: QualityThresholds = DEFAULT_THRESHOLDS,
) -> Diagnosis:
    """Recalifica con un PPI efectivo nuevo usando las métricas ya medidas (sin decodificar)."""
    return _finalize(effective_ppi, diag.sharpness, diag.noise_sigma, diag.blockiness,
                     diag.jpeg_quality, thresholds)


def _finalize(effective_ppi, sharpness, noise, blocks, jpeg_q, thresholds) -> Diagnosis:
    base = classify(effective_ppi, thresholds)
    warnings: list[str] = []
    if sharpness < BLUR_THRESHOLD:
        warnings.append(MSG_BLUR)
    if noise > NOISE_THRESHOLD:
        warnings.append(MSG_NOISE)
    if blocks > BLOCK_THRESHOLD or (jpeg_q is not None and jpeg_q <= LOW_JPEG_QUALITY):
        warnings.append(MSG_BLOCKS)
    level = downgrade(base) if warnings else base
    if base in (QualityLevel.BAJA, QualityLevel.MUY_BAJA):
        warnings.append(f"Pocos píxeles para este tamaño: {effective_ppi:.0f} PPI efectivos.")

    if base in (QualityLevel.BAJA, QualityLevel.MUY_BAJA):
        rec = REC_UPSCALE
    elif not warnings:
        rec = REC_KEEP
    else:
        rec = REC_REVIEW
    return Diagnosis(effective_ppi, base, level, sharpness, noise, blocks, jpeg_q,
                     tuple(warnings), rec)


def analyze(
    info: ImageInfo,
    proxy: Image.Image,
    effective_ppi: float,
    thresholds: QualityThresholds = DEFAULT_THRESHOLDS,
) -> Diagnosis:
    gray = np.asarray(proxy.convert("L"))
    sharpness = measure_sharpness(gray)
    noise = estimate_noise(_resize_long(gray))
    jpeg_q = _jpeg_quality_for(info, proxy)
    full_res = proxy.size == (info.width_px, info.height_px)
    blocks = measure_blockiness(gray) if info.format == "JPEG" and full_res else 1.0
    if hasattr(proxy, "quantization") and getattr(proxy, "quantization", None):
        blocks = measure_blockiness(gray)
    return _finalize(effective_ppi, sharpness, noise, blocks, jpeg_q, thresholds)
