"""Orquestador de mejora: número de pasadas, elección de modelo y caché sin pérdida."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from printmaster.core.color import flatten_alpha
from printmaster.core.enhance.conservative import upscale_conservative
from printmaster.core.enhance.realesrgan import (
    MODEL_ART,
    MODEL_PHOTO,
    EnhanceCancelled,
    EnhanceError,
    RealEsrgan,
)
from printmaster.core.image_loader import load_rgb

log = logging.getLogger("printmaster")

MAX_PASSES = 2
MAX_SIDE_PX = 12000
ART_COLOR_LIMIT = 4096
ENGINE_AI = "Real-ESRGAN"
ENGINE_BASIC = "Mejora básica"

__all__ = ["ENGINE_AI", "ENGINE_BASIC", "EnhanceCancelled", "EnhanceError", "EnhanceResult",
           "Enhancer", "choose_model", "passes_needed"]


def passes_needed(src_ppi: float, target_ppi: float, max_passes: int = MAX_PASSES) -> int:
    n, ppi = 0, src_ppi
    while ppi < target_ppi and n < max_passes:
        ppi *= 4
        n += 1
    return n


def choose_model(proxy: Image.Image) -> str:
    """Ilustraciones y textos planos (pocos colores) → modelo anime; fotos → x4plus."""
    small = proxy.convert("RGB")
    small.thumbnail((256, 256))
    arr = (np.asarray(small) >> 3).astype(np.uint32)
    codes = (arr[..., 0] << 10) | (arr[..., 1] << 5) | arr[..., 2]
    return MODEL_ART if len(np.unique(codes)) < ART_COLOR_LIMIT else MODEL_PHOTO


@dataclass(frozen=True)
class EnhanceResult:
    path: Path
    model: str
    passes: int
    engine: str


def _cap(img: Image.Image) -> Image.Image:
    return _cap_to(img, MAX_SIDE_PX)


def _cap_to(img: Image.Image, limit: int) -> Image.Image:
    side = max(img.size)
    if side <= limit:
        return img
    scale = limit / side
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                      Image.LANCZOS)


class Enhancer:
    def __init__(self, engine: RealEsrgan | None, cache_dir: Path) -> None:
        self.engine = engine
        self.cache_dir = Path(cache_dir)

    def cache_path(self, sha256: str, model: str, passes: int, basic: bool = False) -> Path:
        suffix = "_basica" if basic else ""
        return self.cache_dir / f"{sha256}_{model}_{passes}{suffix}.png"

    def enhance(self, src: Path, sha256: str, passes: int, model: str,
                cancel: threading.Event | None = None,
                progress: Callable[[int, int], None] | None = None) -> EnhanceResult:
        ai_path = self.cache_path(sha256, model, passes)
        basic_path = self.cache_path(sha256, model, passes, basic=True)
        if ai_path.exists():
            return EnhanceResult(ai_path, model, passes, ENGINE_AI)
        if self.engine is None and basic_path.exists():
            return EnhanceResult(basic_path, model, passes, ENGINE_BASIC)
        engine_label = ENGINE_AI if self.engine is not None else ENGINE_BASIC
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="tmp_", dir=self.cache_dir))
        engine = self.engine
        try:
            img, _ = load_rgb(src)
            current = flatten_alpha(img).convert("RGB")
            for k in range(1, passes + 1):
                if cancel is not None and cancel.is_set():
                    raise EnhanceCancelled("Mejora cancelada.")
                # Nunca generar más de MAX_SIDE_PX: si otra pasada lo superaría, la entrada se
                # reduce antes; si ya está cerca del tope, sobran más pasadas.
                if k > 1 and max(current.size) * 2 > MAX_SIDE_PX:
                    if progress is not None:
                        progress(k, passes)
                    continue
                if max(current.size) * 4 > MAX_SIDE_PX:
                    current = _cap_to(current, MAX_SIDE_PX // 4)
                if engine is not None:
                    inp, out = work / f"in_{k}.png", work / f"out_{k}.png"
                    current.save(inp, "PNG")
                    try:
                        engine.upscale_x4(inp, out, model, cancel=cancel)
                        with Image.open(out) as res:
                            current = res.convert("RGB")
                    except EnhanceCancelled:
                        raise
                    except EnhanceError as exc:
                        log.warning("Real-ESRGAN falló; se usa la mejora básica: %s", exc)
                        engine, engine_label = None, ENGINE_BASIC
                        current = upscale_conservative(current, 4)
                else:
                    current = upscale_conservative(current, 4)
                current = _cap(current)
                if progress is not None:
                    progress(k, passes)
            if engine is None:
                engine_label = ENGINE_BASIC
            target = basic_path if engine_label == ENGINE_BASIC else ai_path
            tmp_out = work / "final.png"
            current.save(tmp_out, "PNG")
            os.replace(tmp_out, target)
            return EnhanceResult(target, model, passes, engine_label)
        finally:
            shutil.rmtree(work, ignore_errors=True)
