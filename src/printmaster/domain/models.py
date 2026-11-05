"""Modelos del dominio (inmutables)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


class Orientation(StrEnum):
    AS_ENTERED = "as_entered"  # el ancho es lo que cruza el rollo; nunca se gira
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class FitMode(StrEnum):
    FIT_LENGTH = "largo_auto"  # ancho fijo, largo según la proporción de la imagen
    CONTAIN = "ajustar"
    FILL = "rellenar"
    COVER = "recortar"


class BackgroundKind(StrEnum):
    WHITE = "white"
    COLOR = "color"
    EDGE_COLOR = "edge_color"
    BLUR = "blur"


class EnhanceChoice(StrEnum):
    AUTO = "auto"
    ON = "on"
    OFF = "off"


class ItemStatus(StrEnum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    READY = "ready"
    APPROVED = "approved"
    EXPORTED = "exported"
    ERROR = "error"


@dataclass(frozen=True)
class Background:
    kind: BackgroundKind = BackgroundKind.WHITE
    color: tuple[int, int, int] = (255, 255, 255)


@dataclass(frozen=True)
class CropOffset:
    x: float = 0.5
    y: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(min(1.0, max(0.0, self.x))))
        object.__setattr__(self, "y", float(min(1.0, max(0.0, self.y))))


MIN_CROP_FRACTION = 0.02


@dataclass(frozen=True)
class CropRect:
    """Recorte manual en fracciones (0–1) de la imagen ya orientada: izquierda, arriba,
    derecha, abajo. Se aplica igual a la original y a la mejorada."""

    x0: float = 0.0
    y0: float = 0.0
    x1: float = 1.0
    y1: float = 1.0

    def __post_init__(self) -> None:
        vals = [float(min(1.0, max(0.0, v))) for v in (self.x0, self.y0, self.x1, self.y1)]
        if vals[2] - vals[0] < MIN_CROP_FRACTION or vals[3] - vals[1] < MIN_CROP_FRACTION:
            raise ValueError("El recorte es demasiado pequeño.")
        for name, v in zip(("x0", "y0", "x1", "y1"), vals, strict=True):
            object.__setattr__(self, name, v)

    @property
    def is_full(self) -> bool:
        return (self.x0, self.y0, self.x1, self.y1) == (0.0, 0.0, 1.0, 1.0)

    def box(self, w: int, h: int) -> tuple[int, int, int, int]:
        """Caja en píxeles para una imagen de w×h (al menos 1 px por lado)."""
        left, top = round(self.x0 * w), round(self.y0 * h)
        right = max(left + 1, min(w, round(self.x1 * w)))
        bottom = max(top + 1, min(h, round(self.y1 * h)))
        return left, top, right, bottom


def rotate_region(region: CropRect, inverse: bool = False) -> CropRect:
    """Recorte en coordenadas de la imagen girada 90° a la derecha (o de vuelta)."""
    if inverse:  # (x', y') → (y', 1 - x')
        return CropRect(region.y0, 1 - region.x1, region.y1, 1 - region.x0)
    return CropRect(1 - region.y1, region.x0, 1 - region.y0, region.x1)  # (x, y) → (1 - y, x)


@dataclass(frozen=True)
class PrintSpec:
    width_mm: Decimal
    height_mm: Decimal
    ppi: int = 200
    orientation: Orientation = Orientation.AUTO

    def resolved_for(self, img_w: int, img_h: int) -> PrintSpec:
        if self.orientation == Orientation.AS_ENTERED:
            return self
        short, long_ = sorted((self.width_mm, self.height_mm))
        if self.orientation == Orientation.PORTRAIT:
            return replace(self, width_mm=short, height_mm=long_)
        if self.orientation == Orientation.LANDSCAPE:
            return replace(self, width_mm=long_, height_mm=short)
        if img_w > img_h:
            return replace(self, width_mm=long_, height_mm=short,
                           orientation=Orientation.LANDSCAPE)
        if img_h > img_w:
            return replace(self, width_mm=short, height_mm=long_,
                           orientation=Orientation.PORTRAIT)
        kept = (Orientation.LANDSCAPE if self.width_mm > self.height_mm
                else Orientation.PORTRAIT)
        return replace(self, orientation=kept)


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    format: str
    width_px: int
    height_px: int
    mode: str
    has_alpha: bool
    icc: bytes | None = field(default=None, repr=False)
    exif_orientation: int = 1
    file_size: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class RenderPlan:
    page_w_mm: Decimal
    page_h_mm: Decimal
    page_w_pt: float
    page_h_pt: float
    src_box: tuple[int, int, int, int]
    dest_rect_pt: tuple[float, float, float, float]
    output_px: tuple[int, int] | None
    compose_page: bool
    background: Background
    effective_ppi: float
    passthrough: bool
    rotate: bool = False  # la imagen se gira 90° a la derecha antes de recortar (src_box)
