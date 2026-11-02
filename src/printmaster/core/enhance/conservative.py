"""Mejora básica sin IA: Lanczos y un enfoque suave (no inventa contenido)."""

from __future__ import annotations

from PIL import Image, ImageFilter


def upscale_conservative(img: Image.Image, factor: int) -> Image.Image:
    size = (img.width * factor, img.height * factor)
    up = img.resize(size, Image.LANCZOS)
    return up.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
