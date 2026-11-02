from decimal import Decimal as D

import pikepdf
import pytest
from PIL import Image
from pypdf import PdfReader

from printmaster.core.composer import render_raster
from printmaster.core.image_loader import load_rgb, probe
from printmaster.core.layout import plan
from printmaster.core.pdf_writer import ExportOptions, PdfExportError, write_pdf
from printmaster.domain.models import FitMode, PrintSpec
from printmaster.domain.units import Unit, mm_to_pt, to_mm


def export(src, out, spec, mode=FitMode.CONTAIN, options=ExportOptions()):
    info = probe(src)
    p = plan(info, spec, mode)
    write_pdf(info, p, out, options)
    return info, p, PdfReader(str(out))


def xobject(reader):
    return reader.pages[0]["/Resources"]["/XObject"]["/Im0"].get_object()


FORMATS = [
    (60, 45, Unit.CM), (60, 90, Unit.CM), (60, 120, Unit.CM), (50, 70, Unit.CM),
    (40, 60, Unit.CM), (60, 150, Unit.CM), (600, 900, Unit.MM), (24, 36, Unit.IN),
]


@pytest.mark.parametrize("w,h,unit", FORMATS)
@pytest.mark.parametrize("mode", [FitMode.CONTAIN, FitMode.COVER])
def test_exact_page_size(make_image, tmp_path, w, h, unit, mode):
    src = make_image("a.jpg", size=(1200, 900))
    spec = PrintSpec(to_mm(w, unit), to_mm(h, unit))
    _, p, reader = export(src, tmp_path / "a.pdf", spec, mode)
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert abs(float(box.width) - mm_to_pt(p.page_w_mm)) < 0.01
    assert abs(float(box.height) - mm_to_pt(p.page_h_mm)) < 0.01
    assert {p.page_w_mm, p.page_h_mm} == {to_mm(w, unit), to_mm(h, unit)}
    prefs = reader.trailer["/Root"]["/ViewerPreferences"]
    assert prefs["/PrintScaling"] == "/None"


def test_passthrough_is_byte_identical(make_image, tmp_path):
    src = make_image("a.jpg", size=(1200, 900))
    _, p, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(600), D(450)))
    assert p.passthrough
    xo = xobject(reader)
    assert xo["/Filter"] == "/DCTDecode"
    assert xo._data == src.read_bytes()


def test_cover_passthrough_overflows_page(make_image, tmp_path):
    src = make_image("a.jpg", size=(1200, 900))
    _, p, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(500), D(500)), FitMode.COVER)
    assert p.passthrough
    tokens = reader.pages[0].get_contents().get_data().split()
    i = tokens.index(b"cm")
    width = float(tokens[i - 6])
    assert width > p.page_w_pt + 1


def test_png_lossless_pixels(make_image, tmp_path):
    src = make_image("a.png", size=(300, 200))
    info, p, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(100)))
    xo = xobject(reader)
    assert xo["/Filter"] == "/FlateDecode"
    expected = render_raster(load_rgb(src)[0], p).tobytes()
    assert xo.get_data() == expected


def test_icc_embedded(make_image, tmp_path):
    src = make_image("a.png", size=(300, 200))
    _, _, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(100)))
    cs = xobject(reader)["/ColorSpace"]
    assert cs[0] == "/ICCBased"
    assert cs[1].get_object()["/N"] == 3


def test_alpha_flattened_white(tmp_path):
    src = tmp_path / "logo.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(src)
    _, _, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(100)))
    xo = xobject(reader)
    assert "/SMask" not in xo
    data = xo.get_data()
    mid = (25 * 50 + 25) * 3
    assert data[mid:mid + 3] == b"\xff\xff\xff"


def test_alpha_kept_with_smask(tmp_path):
    src = tmp_path / "logo.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(src)
    _, _, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(100)),
                          options=ExportOptions(keep_alpha=True))
    assert "/SMask" in xobject(reader)


def test_cmyk_jpeg_converted(tmp_path):
    src = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (64, 64), (0, 255, 0, 0)).save(src, "JPEG")
    _, p, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(100)))
    assert not p.passthrough
    assert xobject(reader)["/ColorSpace"][1].get_object()["/N"] == 3


def test_lossy_reencode_for_jpeg_source(make_image, tmp_path):
    src = make_image("big.jpg", size=(4000, 3000))
    _, p, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(75)),
                          options=ExportOptions(lossless=False))
    assert p.output_px is not None
    assert xobject(reader)["/Filter"] == "/DCTDecode"


def test_lossy_option_ignored_for_png(make_image, tmp_path):
    src = make_image("big.png", size=(2000, 1500))
    _, _, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(75)),
                          options=ExportOptions(lossless=False))
    assert xobject(reader)["/Filter"] == "/FlateDecode"


def test_unicode_output_folder_atomic(make_image, tmp_path):
    src = make_image("a.jpg")
    out = tmp_path / "Salida Peña" / "x.pdf"
    export(src, out, PrintSpec(D(100), D(100)))
    assert out.exists()
    assert not list(out.parent.glob("*.tmp"))


def test_failure_leaves_nothing(make_image, tmp_path, monkeypatch):
    src = make_image("a.jpg")
    out = tmp_path / "x.pdf"

    def boom(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(pikepdf.Pdf, "save", boom)
    info = probe(src)
    with pytest.raises(PdfExportError):
        write_pdf(info, plan(info, PrintSpec(D(100), D(100)), FitMode.CONTAIN), out)
    assert not out.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_exif_rotated_image_upright(make_image, tmp_path):
    src = make_image("rot.jpg", size=(400, 300), exif_orientation=6)
    _, p, reader = export(src, tmp_path / "a.pdf", PrintSpec(D(300), D(400)))
    xo = xobject(reader)
    assert xo["/Height"] > xo["/Width"]
    assert not p.passthrough


def test_background_color_rect(make_image, tmp_path):
    from printmaster.domain.models import Background, BackgroundKind
    src = make_image("a.jpg", size=(300, 600))
    info = probe(src)
    p = plan(info, PrintSpec(D(400), D(400)), FitMode.FILL,
             Background(BackgroundKind.COLOR, (255, 0, 0)))
    write_pdf(info, p, tmp_path / "a.pdf")
    content = PdfReader(str(tmp_path / "a.pdf")).pages[0].get_contents().get_data()
    assert b"1 0 0 rg" in content and b"re f" in content


def test_original_untouched(make_image, tmp_path):
    src = make_image("a.jpg")
    before = src.read_bytes()
    export(src, tmp_path / "a.pdf", PrintSpec(D(100), D(100)), FitMode.COVER)
    assert src.read_bytes() == before
