"""Utilidades de color: perfil sRGB, transparencia y color de borde."""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageCms


@lru_cache(maxsize=1)
def srgb_icc() -> bytes:
    """Perfil ICC sRGB serializado (para incrustar en PDF o tras convertir CMYK)."""
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
