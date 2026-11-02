"""Planificación del ajuste de una imagen a la página (función pura).

La vista previa y el PDF dibujan exactamente el mismo RenderPlan.
Coordenadas de destino en puntos PDF con origen abajo a la izquierda.
"""

from __future__ import annotations

import math
from decimal import Decimal

from printmaster.domain.models import (
    Background,
    BackgroundKind,
    CropOffset,
    FitMode,
    ImageInfo,
    Orientation,
    PrintSpec,
    RenderPlan,
)
from printmaster.domain.units import mm_to_pt, mm_to_px

DOWNSAMPLE_TOLERANCE = 1.01


def _pt_to_mm(pt: float) -> Decimal:
    return Decimal(str(pt)) * Decimal("25.4") / Decimal(72)


def auto_length_mm(width_mm: Decimal, img_w: int, img_h: int, step_mm: int = 50) -> Decimal:
    """Largo de lámina para que la imagen ocupe todo el ancho, redondeado hacia arriba."""
    exact = Decimal(width_mm) * Decimal(img_h) / Decimal(img_w)
    steps = math.ceil(float(exact / Decimal(step_mm)) - 1e-9)
    return Decimal(max(1, steps) * step_mm)


def _resolved_spec(info: ImageInfo, spec: PrintSpec, mode: FitMode,
                   length_step_mm: int, aspect_px: tuple[int, int] | None = None) -> PrintSpec:
    if mode == FitMode.FIT_LENGTH:
        aw, ah = aspect_px or (info.width_px, info.height_px)
        length = auto_length_mm(spec.width_mm, aw, ah, length_step_mm)
        return PrintSpec(spec.width_mm, length, spec.ppi, Orientation.AS_ENTERED)
    return spec.resolved_for(info.width_px, info.height_px)


def page_size_mm(info: ImageInfo, spec: PrintSpec, mode: FitMode,
                 length_step_mm: int = 50,
                 aspect_px: tuple[int, int] | None = None) -> tuple[Decimal, Decimal]:
    """aspect_px: proporción para el largo automático (la del original, aunque se imprima la
    versión mejorada, cuyo redondeo de píxeles podría cambiar el largo)."""
    s = _resolved_spec(info, spec, mode, length_step_mm, aspect_px)
    return s.width_mm, s.height_mm


def plan(
    info: ImageInfo,
    spec: PrintSpec,
    mode: FitMode,
    background: Background = Background(),
    crop: CropOffset = CropOffset(),
    length_step_mm: int = 50,
    aspect_px: tuple[int, int] | None = None,
) -> RenderPlan:
    if background.kind == BackgroundKind.EDGE_COLOR:
        raise ValueError("El color de borde debe resolverse antes de planificar.")
    W, H = info.width_px, info.height_px
    s = _resolved_spec(info, spec, mode, length_step_mm, aspect_px)
    page_w_pt, page_h_pt = mm_to_pt(s.width_mm), mm_to_pt(s.height_mm)

    if mode == FitMode.COVER:
        aspect = page_w_pt / page_h_pt
        if W / H > aspect:
            sh = H
            sw = min(W, max(1, round(H * aspect)))
        else:
            sw = W
            sh = min(H, max(1, round(W / aspect)))
        left = round((W - sw) * crop.x)
        top = round((H - sh) * crop.y)
        src_box = (left, top, left + sw, top + sh)
        dest = (0.0, 0.0, page_w_pt, page_h_pt)
    else:
        scale = min(page_w_pt / W, page_h_pt / H)
        dw, dh = W * scale, H * scale
        dest = ((page_w_pt - dw) / 2, (page_h_pt - dh) / 2, dw, dh)
        src_box = (0, 0, W, H)

    if mode in (FitMode.CONTAIN, FitMode.FIT_LENGTH):
        background = Background()

    sw, sh = src_box[2] - src_box[0], src_box[3] - src_box[1]
    eff = min(sw / (dest[2] / 72), sh / (dest[3] / 72))

    compose_page = mode == FitMode.FILL and background.kind == BackgroundKind.BLUR
    if compose_page:
        ppi = max(1, round(min(s.ppi, eff)))
        output_px: tuple[int, int] | None = (
            max(1, mm_to_px(s.width_mm, ppi)),
            max(1, mm_to_px(s.height_mm, ppi)),
        )
        dest = (0.0, 0.0, page_w_pt, page_h_pt)
    elif eff > s.ppi * DOWNSAMPLE_TOLERANCE:
        output_px = (
            max(1, mm_to_px(_pt_to_mm(dest[2]), s.ppi)),
            max(1, mm_to_px(_pt_to_mm(dest[3]), s.ppi)),
        )
    else:
        output_px = None

    passthrough = (
        info.format == "JPEG"
        and info.mode in {"RGB", "L"}
        and info.exif_orientation in {0, 1}
        and output_px is None
        and not compose_page
    )
    return RenderPlan(
        page_w_mm=s.width_mm,
        page_h_mm=s.height_mm,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        src_box=src_box,
        dest_rect_pt=dest,
        output_px=output_px,
        compose_page=compose_page,
        background=background,
        effective_ppi=eff,
        passthrough=passthrough,
    )


def full_image_rect_pt(
    plan: RenderPlan, img_w: int, img_h: int
) -> tuple[float, float, float, float]:
    """Rectángulo de la imagen completa a la escala del plan (para recorte sin recomprimir)."""
    l, t, r, b = plan.src_box
    x, y, w, h = plan.dest_rect_pt
    sx, sy = w / (r - l), h / (b - t)
    full_w, full_h = img_w * sx, img_h * sy
    # y PDF crece hacia arriba: el borde inferior de la imagen queda (img_h - b) px debajo.
    return (x - l * sx, y - (img_h - b) * sy, full_w, full_h)
