"""Generación de un PDF por imagen con dimensiones físicas exactas.

Se construye el PDF a bajo nivel con pikepdf para controlar:
- MediaBox exacto en puntos, sin márgenes añadidos;
- incrustación byte a byte del JPEG original cuando no hace falta transformarlo;
- perfil ICC incrustado (ICCBased) para evitar cambios de color;
- transparencia como SMask opcional;
- /ViewerPreferences /PrintScaling /None para que el visor no escale al imprimir.
"""

from __future__ import annotations

import io
import os
import zlib
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name

from printmaster import __version__
from printmaster.core.color import srgb_icc
from printmaster.core.composer import render_raster
from printmaster.core.image_loader import load_rgb
from printmaster.core.layout import full_image_rect_pt
from printmaster.domain.models import BackgroundKind, ImageInfo, RenderPlan


@dataclass(frozen=True)
class ExportOptions:
    lossless: bool = True
    jpeg_quality: int = 95
    keep_alpha: bool = False


class PdfExportError(Exception):
    """No se pudo escribir el PDF."""


def _num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def _icc_channels(icc: bytes) -> int | None:
    """Número de canales según la cabecera ICC (bytes 16-19)."""
    if len(icc) < 20:
        return None
    return {b"RGB ": 3, b"GRAY": 1, b"CMYK": 4}.get(icc[16:20])


def _colorspace(pdf: pikepdf.Pdf, channels: int, icc: bytes | None):
    if icc is None and channels == 3:
        icc = srgb_icc()
    if icc is not None and _icc_channels(icc) == channels:
        alternate = Name.DeviceRGB if channels == 3 else Name.DeviceGray
        stream = pikepdf.Stream(pdf, zlib.compress(icc, 6))
        stream.N = channels
        stream.Alternate = alternate
        stream.Filter = Name.FlateDecode
        return Array([Name.ICCBased, stream])
    if channels == 3:
        return _colorspace(pdf, 3, srgb_icc())
    return Name.DeviceGray


def _image_stream(pdf, data: bytes, width: int, height: int, filter_: Name, colorspace):
    stream = pikepdf.Stream(pdf, data)
    stream.Type = Name.XObject
    stream.Subtype = Name.Image
    stream.Width = width
    stream.Height = height
    stream.BitsPerComponent = 8
    stream.ColorSpace = colorspace
    stream.Filter = filter_
    return stream


def _build_image(pdf: pikepdf.Pdf, info: ImageInfo, plan: RenderPlan, options: ExportOptions):
    """Devuelve (stream de imagen, rectángulo destino en pt)."""
    if plan.passthrough:
        channels = 1 if info.mode == "L" else 3
        stream = _image_stream(pdf, info.path.read_bytes(), info.width_px, info.height_px,
                               Name.DCTDecode, _colorspace(pdf, channels, info.icc))
        rect = full_image_rect_pt(plan, info.width_px, info.height_px)
        return stream, rect

    img, icc = load_rgb(info.path)
    keep_alpha = options.keep_alpha and img.mode == "RGBA"
    out = render_raster(img, plan, keep_alpha=keep_alpha)
    alpha = out.getchannel("A") if out.mode == "RGBA" else None
    color = out.convert("RGB") if out.mode == "RGBA" else out
    if color.mode not in ("RGB", "L"):
        color = color.convert("RGB")
    channels = 3 if color.mode == "RGB" else 1
    colorspace = _colorspace(pdf, channels, icc)

    if not options.lossless and info.format == "JPEG":
        buf = io.BytesIO()
        color.save(buf, "JPEG", quality=options.jpeg_quality, subsampling=0, optimize=True)
        data, filter_ = buf.getvalue(), Name.DCTDecode
    else:
        data, filter_ = zlib.compress(color.tobytes(), 6), Name.FlateDecode
    stream = _image_stream(pdf, data, color.width, color.height, filter_, colorspace)

    if alpha is not None:
        smask = _image_stream(pdf, zlib.compress(alpha.tobytes(), 6), alpha.width,
                              alpha.height, Name.FlateDecode, Name.DeviceGray)
        stream.SMask = smask
    return stream, plan.dest_rect_pt


def _content(plan: RenderPlan, rect) -> bytes:
    parts = []
    bg = plan.background
    if bg.kind == BackgroundKind.COLOR:
        r, g, b = (c / 255 for c in bg.color)
        parts.append(f"q {_num(r)} {_num(g)} {_num(b)} rg 0 0 "
                     f"{_num(plan.page_w_pt)} {_num(plan.page_h_pt)} re f Q")
    x, y, w, h = rect
    parts.append(f"q {_num(w)} 0 0 {_num(h)} {_num(x)} {_num(y)} cm /Im0 Do Q")
    return "\n".join(parts).encode("ascii")


def write_pdf(
    info: ImageInfo, plan: RenderPlan, out_path: Path, options: ExportOptions = ExportOptions()
) -> Path:
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.name + ".tmp")
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pdf = pikepdf.new()
        pdf.add_blank_page(page_size=(plan.page_w_pt, plan.page_h_pt))
        page = pdf.pages[0]
        page.MediaBox = Array([0, 0, plan.page_w_pt, plan.page_h_pt])
        image, rect = _build_image(pdf, info, plan, options)
        page.Resources = Dictionary(XObject=Dictionary(Im0=image))
        page.Contents = pdf.make_stream(_content(plan, rect))
        pdf.Root.ViewerPreferences = Dictionary(PrintScaling=Name("/None"))
        w_mm = f"{plan.page_w_mm.normalize():f}"
        h_mm = f"{plan.page_h_mm.normalize():f}"
        pdf.docinfo["/Title"] = info.path.name
        pdf.docinfo["/Creator"] = f"PrintMaster Studio {__version__}"
        pdf.docinfo["/Subject"] = f"{w_mm}×{h_mm} mm · {plan.effective_ppi:.0f} PPI efectivos"
        pdf.save(tmp)
        os.replace(tmp, out_path)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo se reporta igual
        tmp.unlink(missing_ok=True)
        raise PdfExportError(f"No se pudo generar «{out_path.name}»: {exc}") from exc
    return out_path


__all__ = ["ExportOptions", "PdfExportError", "write_pdf"]
