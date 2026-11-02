"""Modelos del dominio (inmutables)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


class Orientation(StrEnum):
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class FitMode(StrEnum):
    CONTAIN = "ajustar"
    FILL = "rellenar"
    COVER = "recortar"


class BackgroundKind(StrEnum):
    WHITE = "white"
    COLOR = "color"
    EDGE_COLOR = "edge_color"
    BLUR = "blur"


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


@dataclass(frozen=True)
class PrintSpec:
    width_mm: Decimal
    height_mm: Decimal
    ppi: int = 200
    orientation: Orientation = Orientation.AUTO

    def resolved_for(self, img_w: int, img_h: int) -> PrintSpec:
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
