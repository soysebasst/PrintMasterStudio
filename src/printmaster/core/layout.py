"""Planificación del ajuste de una imagen a la página (función pura).

La vista previa y el PDF dibujan exactamente el mismo RenderPlan.
Coordenadas de destino en puntos PDF con origen abajo a la izquierda.
"""

from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal

from printmaster.domain.models import (
    Background,
    BackgroundKind,
    CropOffset,
    CropRect,
    FitMode,
    ImageInfo,
    Orientation,
    PrintSpec,
    RenderPlan,
    rotate_region,
)
from printmaster.domain.units import mm_to_pt, mm_to_px

DOWNSAMPLE_TOLERANCE = 1.01


def _pt_to_mm(pt: float) -> Decimal:
    return Decimal(str(pt)) * Decimal("25.4") / Decimal(72)


# En «Largo auto» la lámina se ajusta al milímetro y la imagen la llena (se pierde menos de
# 1 mm). Si la fuente impresa tiene otra proporción (Gemini la recortó), se ajusta sin cortar.
FIT_LENGTH_FILL_TOLERANCE = 0.02


def auto_length_mm(width_mm: Decimal, img_w: int, img_h: int, step_mm: int = 50) -> Decimal:
    """Largo de lámina para que la imagen ocupe todo el ancho, redondeado hacia arriba."""
    exact = Decimal(width_mm) * Decimal(img_h) / Decimal(img_w)
    steps = math.ceil(float(exact / Decimal(step_mm)) - 1e-9)
    return Decimal(max(1, steps) * step_mm)


def _region_dims(w: float, h: float, region: CropRect) -> tuple[float, float]:
    return w * (region.x1 - region.x0), h * (region.y1 - region.y0)


def _resolved_spec(info: ImageInfo, spec: PrintSpec, mode: FitMode,
                   length_step_mm: int, aspect_px: tuple[int, int] | None = None,
                   region: CropRect = CropRect()) -> PrintSpec:
    if mode == FitMode.FIT_LENGTH:
        aw, ah = aspect_px or (info.width_px, info.height_px)
        rw, rh = _region_dims(aw, ah, region)
        exact = Decimal(spec.width_mm) * Decimal(repr(rh)) / Decimal(repr(rw))
        # lámina justa (al milímetro, hacia arriba): sin franjas; el cobro va por tramos
        length = Decimal(max(1, math.ceil(float(exact) - 1e-9)))
        return PrintSpec(spec.width_mm, length, spec.ppi, Orientation.AS_ENTERED)
    rw, rh = _region_dims(info.width_px, info.height_px, region)
    return spec.resolved_for(max(1, round(rw)), max(1, round(rh)))


def page_size_mm(info: ImageInfo, spec: PrintSpec, mode: FitMode,
                 length_step_mm: int = 50,
                 aspect_px: tuple[int, int] | None = None,
                 region: CropRect = CropRect(),
                 rotate: bool = False) -> tuple[Decimal, Decimal]:
    """aspect_px: proporción para el largo automático (la del original, aunque se imprima la
    versión mejorada, cuyo redondeo de píxeles podría cambiar el largo). region: recorte
    manual, en fracciones de la imagen."""
    if rotate:
        info, region, aspect_px = _rotated(info, region, aspect_px)
    s = _resolved_spec(info, spec, mode, length_step_mm, aspect_px, region)
    return s.width_mm, s.height_mm


def _rotated(info: ImageInfo, region: CropRect, aspect_px: tuple[int, int] | None):
    """Datos de la imagen como si ya estuviera girada 90° a la derecha."""
    turned = replace(info, width_px=info.height_px, height_px=info.width_px)
    aspect = (aspect_px[1], aspect_px[0]) if aspect_px else None
    return turned, rotate_region(region), aspect


def plan(
    info: ImageInfo,
    spec: PrintSpec,
    mode: FitMode,
    background: Background = Background(),
    crop: CropOffset = CropOffset(),
    length_step_mm: int = 50,
    aspect_px: tuple[int, int] | None = None,
    region: CropRect = CropRect(),
    rotate: bool = False,
) -> RenderPlan:
    """rotate: imprime la imagen girada 90° a la derecha (src_box queda en coordenadas de la
    imagen girada y no se incrusta el JPEG original)."""
    if background.kind == BackgroundKind.EDGE_COLOR:
        raise ValueError("El color de borde debe resolverse antes de planificar.")
    if rotate:
        info, region, aspect_px = _rotated(info, region, aspect_px)
    rl, rt, rr, rb = region.box(info.width_px, info.height_px)
    W, H = rr - rl, rb - rt  # se planifica sobre la zona recortada
    s = _resolved_spec(info, spec, mode, length_step_mm, aspect_px, region)
    page_w_pt, page_h_pt = mm_to_pt(s.width_mm), mm_to_pt(s.height_mm)

    fill_length = (mode == FitMode.FIT_LENGTH
                   and abs((W / H) / (page_w_pt / page_h_pt) - 1) <= FIT_LENGTH_FILL_TOLERANCE)
    if mode == FitMode.COVER or fill_length:  # el largo justo también llena la lámina
        aspect = page_w_pt / page_h_pt
        if W / H > aspect:
            sh = H
            sw = min(W, max(1, round(H * aspect)))
        else:
            sw = W
            sh = min(H, max(1, round(W / aspect)))
        left = rl + round((W - sw) * crop.x)
        top = rt + round((H - sh) * crop.y)
        src_box = (left, top, left + sw, top + sh)
        dest = (0.0, 0.0, page_w_pt, page_h_pt)
    else:
        scale = min(page_w_pt / W, page_h_pt / H)
        dw, dh = W * scale, H * scale
        dest = ((page_w_pt - dw) / 2, (page_h_pt - dh) / 2, dw, dh)
        src_box = (rl, rt, rr, rb)

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
        and not rotate
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
        rotate=rotate,
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
