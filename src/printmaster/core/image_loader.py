"""Lectura segura de imágenes de clientes.

El archivo original nunca se modifica. Todas las rutas se abren con Pillow, que maneja
rutas Unicode en Windows (OpenCV no debe abrir archivos directamente).
"""

from __future__ import annotations

import hashlib
import io
import re
import warnings
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps

from printmaster.core.color import srgb_icc
from printmaster.domain.models import ImageInfo

Image.MAX_IMAGE_PIXELS = 400_000_000

SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"})

_ORIENTATION_TAG = 0x0112
_ALPHA_MODES = {"RGBA", "LA", "PA", "RGBa", "La"}


class ImageLoadError(Exception):
    """La imagen no se pudo leer (corrupta, inexistente, demasiado grande o no soportada)."""


def _error(path: Path, exc: BaseException) -> ImageLoadError:
    if isinstance(exc, FileNotFoundError):
        detail = "el archivo no existe"
    elif isinstance(exc, (Image.DecompressionBombError, Image.DecompressionBombWarning)):
        detail = "la imagen es demasiado grande"
    elif isinstance(exc, Image.UnidentifiedImageError):
        detail = "formato no reconocido o archivo dañado"
    else:
        detail = str(exc) or exc.__class__.__name__
    return ImageLoadError(f"No se pudo leer «{path.name}»: {detail}.")


def _open(path: Path) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        return Image.open(path)


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in _ALPHA_MODES or "transparency" in img.info


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> ImageInfo:
    """Metadatos sin decodificar píxeles. Dimensiones ya corregidas por EXIF."""
    path = Path(path)
    try:
        with _open(path) as img:
            orientation = int(img.getexif().get(_ORIENTATION_TAG, 1) or 1)
            w, h = img.size
            if orientation in (5, 6, 7, 8):
                w, h = h, w
            info = ImageInfo(
                path=path,
                format=img.format or "",
                width_px=w,
                height_px=h,
                mode=img.mode,
                has_alpha=_has_alpha(img),
                icc=img.info.get("icc_profile") or None,
                exif_orientation=orientation,
                file_size=path.stat().st_size,
                sha256=_sha256(path),
            )
    except ImageLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de lectura se reporta igual
        raise _error(path, exc) from exc
    return info


def _to_8bit_gray(img: Image.Image) -> Image.Image:
    arr = np.asarray(img)
    if arr.dtype.kind == "f":
        arr = np.clip(arr, 0, 255)
    elif arr.max(initial=0) > 255:
        arr = arr / 257.0
    return Image.fromarray(np.round(arr).astype(np.uint8), "L")


def _normalize(img: Image.Image) -> tuple[Image.Image, bytes | None]:
    """Primer cuadro, EXIF aplicado, modo final en {RGB, RGBA, L} y su ICC."""
    try:
        img.seek(0)
    except EOFError:
        pass
    icc = img.info.get("icc_profile") or None
    alpha = _has_alpha(img)
    img = ImageOps.exif_transpose(img)
    mode = img.mode
    if mode == "CMYK":
        if icc:
            try:
                src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                dst = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
                img = ImageCms.profileToProfile(img, src, dst, outputMode="RGB")
            except (ImageCms.PyCMSError, OSError):
                img = img.convert("RGB")
        else:
            img = img.convert("RGB")
        return img, srgb_icc()
    if mode in ("I;16", "I;16B", "I;16L", "I;16N", "I", "F"):
        return _to_8bit_gray(img), None
    if mode in ("RGB", "L"):
        if alpha:  # transparencia por color clave
            return img.convert("RGBA"), icc
        return img, icc
    if mode == "RGBA":
        return img, icc
    if mode in ("P", "LA", "PA", "La", "RGBa"):
        return img.convert("RGBA" if alpha else "RGB"), icc
    if mode == "1":
        return img.convert("L"), icc
    return img.convert("RGB"), None


def load_rgb(path: Path) -> tuple[Image.Image, bytes | None]:
    """Imagen completa normalizada (RGB/RGBA/L) y su perfil ICC."""
    path = Path(path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                img.load()
                out, icc = _normalize(img)
                out.load()
                return out, icc
    except Exception as exc:  # noqa: BLE001
        raise _error(path, exc) from exc


def load_proxy(path: Path, max_side: int = 2048) -> Image.Image:
    """Copia reducida en RGB (transparencia sobre blanco) para análisis y vista previa."""
    path = Path(path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                if img.format == "JPEG" and img.mode in ("RGB", "L"):
                    img.draft(img.mode, (max_side, max_side))
                img.load()
                out, _ = _normalize(img)
                out = out.copy()
    except Exception as exc:  # noqa: BLE001
        raise _error(path, exc) from exc
    out.thumbnail((max_side, max_side), Image.LANCZOS)
    if out.mode == "RGBA":
        bg = Image.new("RGB", out.size, (255, 255, 255))
        bg.paste(out, mask=out.getchannel("A"))
        out = bg
    elif out.mode != "RGB":
        out = out.convert("RGB")
    return out


def make_thumbnail(path: Path, max_side: int = 256) -> Image.Image:
    return load_proxy(path, max_side=max_side)


def _natural_key(path: Path) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(path))]


def collect_images(paths: Iterable[Path]) -> list[Path]:
    """Expande carpetas (recursivo), filtra extensiones soportadas, quita duplicados."""
    found: dict[Path, Path] = {}
    for raw in paths:
        p = Path(raw)
        candidates = (sorted(c for c in p.rglob("*") if c.is_file()) if p.is_dir() else [p])
        for c in candidates:
            if c.suffix.lower() in SUPPORTED_EXTENSIONS and c.is_file():
                found.setdefault(c.resolve(), c)
    return sorted(found.values(), key=_natural_key)
