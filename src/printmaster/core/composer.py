"""Ejecución raster de un RenderPlan (recorte, remuestreo, fondo, transparencia)."""

from __future__ import annotations

from PIL import Image, ImageFilter

from printmaster.core.color import flatten_alpha
from printmaster.domain.models import RenderPlan


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _compose_blur_page(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    base = flatten_alpha(img).convert("RGB")
    background = _cover(base, size).filter(
        ImageFilter.GaussianBlur(radius=max(4, 0.02 * max(w, h))))
    scale = min(w / img.width, h / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                    Image.LANCZOS)
    pos = ((w - fg.width) // 2, (h - fg.height) // 2)
    if fg.mode == "RGBA":
        background.paste(fg, pos, mask=fg.getchannel("A"))
    else:
        background.paste(fg.convert("RGB"), pos)
    return background


def render_raster(img: Image.Image, plan: RenderPlan, keep_alpha: bool = False) -> Image.Image:
    """Imagen final en píxeles lista para incrustar en el PDF."""
    if plan.rotate:
        img = img.transpose(Image.Transpose.ROTATE_270)  # 90° a la derecha
    out = img.crop(plan.src_box) if plan.src_box != (0, 0, img.width, img.height) else img
    if plan.compose_page:
        assert plan.output_px is not None
        return _compose_blur_page(out, plan.output_px)
    if plan.output_px is not None and plan.output_px != out.size:
        out = out.resize(plan.output_px, Image.LANCZOS)
    if not keep_alpha:
        out = flatten_alpha(out)
    return out
