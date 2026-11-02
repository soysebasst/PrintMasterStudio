"""Utilidades de color: perfil sRGB, transparencia y color de borde."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageCms


@lru_cache(maxsize=1)
def srgb_icc() -> bytes:
    """Perfil ICC sRGB serializado (para incrustar en PDF o tras convertir CMYK)."""
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def flatten_alpha(img: Image.Image, color: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Aplana RGBA sobre un color sólido (blanco por defecto: el plotter no imprime blanco)."""
    if img.mode != "RGBA":
        return img
    bg = Image.new("RGB", img.size, color)
    bg.paste(img, mask=img.getchannel("A"))
    return bg


def edge_color(img: Image.Image, band: float = 0.02) -> tuple[int, int, int]:
    """Mediana del color de una banda del borde (para el fondo "Color del borde")."""
    arr = np.asarray(flatten_alpha(img).convert("RGB"))
    h, w = arr.shape[:2]
    bw, bh = max(1, round(w * band)), max(1, round(h * band))
    pixels = np.concatenate([
        arr[:bh].reshape(-1, 3), arr[-bh:].reshape(-1, 3),
        arr[:, :bw].reshape(-1, 3), arr[:, -bw:].reshape(-1, 3),
    ])
    r, g, b = np.median(pixels, axis=0)
    return int(r), int(g), int(b)
