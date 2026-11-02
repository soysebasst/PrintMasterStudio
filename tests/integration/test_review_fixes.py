"""Pruebas de los hallazgos de la revisión final (Fase 1)."""

import io
from datetime import date
from decimal import Decimal as D

import pytest
from PIL import Image
from pypdf import PdfReader
from tests.conftest import texture_array

from printmaster.app_services import job_controller as jc_mod
from printmaster.app_services.job_controller import JobController
from printmaster.core.image_analyzer import analyze
from printmaster.core.image_loader import load_proxy, probe
from printmaster.core.layout import plan
from printmaster.core.pdf_writer import write_pdf
from printmaster.domain.models import FitMode, ItemStatus, Orientation, PrintSpec
from printmaster.domain.quality import QualityLevel
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile

TODAY = date(2026, 11, 2)


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    c = JobController(Settings(output_dir=tmp_path / "out"), load_profile())
    c.set_spec(PrintSpec(D(100), D(150), orientation=Orientation.PORTRAIT))
    return c


def ready_batch(ctrl, make_image, tmp_path, n=4, size=(800, 1200)):
    files = [make_image(f"i{i}.jpg", size=size, seed=i, folder=tmp_path / "in") for i in range(n)]
    ctrl.add_paths(files)
    for i in range(n):
        ctrl.analyze(i)
    return files


# Crítico 1: parámetros congelados durante la exportación
def test_export_uses_params_frozen_at_start(ctrl, make_image, tmp_path, monkeypatch):
    ready_batch(ctrl, make_image, tmp_path)
    ctrl.approve_all()
    real = jc_mod.write_pdf
    calls = []

    def spy(info, p, out, options):
        calls.append(1)
        if len(calls) == 1:  # el usuario cambia el formato a mitad de la exportación
            ctrl.set_spec(PrintSpec(D(400), D(600), orientation=Orientation.PORTRAIT))
        return real(info, p, out, options)

    monkeypatch.setattr(jc_mod, "write_pdf", spy)
    results = ctrl.export(None, tmp_path / "out", today=TODAY)
    widths = {round(float(PdfReader(str(r.output)).pages[0].mediabox.width), 1)
              for r in results}
    assert widths == {283.5}
    assert all(r.ok for r in results)


# Importante 2/8: la recalificación por cambio de formato es inmediata y no decodifica
def test_spec_change_rerates_immediately(ctrl, make_image, tmp_path, monkeypatch):
    ready_batch(ctrl, make_image, tmp_path)
    assert all(it.diagnosis.level != QualityLevel.MUY_BAJA for it in ctrl.items)

    def no_decode(*a, **k):
        raise AssertionError("no debe decodificar al cambiar el formato")

    monkeypatch.setattr(jc_mod, "load_proxy", no_decode)
    ctrl.set_spec(PrintSpec(D(600), D(1500), orientation=Orientation.PORTRAIT))
    assert all(it.diagnosis.level in (QualityLevel.BAJA, QualityLevel.MUY_BAJA)
               for it in ctrl.items)
    assert ctrl.approve_all() == [0, 1, 2, 3]


# Importante 3: un ítem en ERROR por exportación puede recuperarse
def test_error_item_recovers(ctrl, make_image, tmp_path, monkeypatch):
    ready_batch(ctrl, make_image, tmp_path, n=1)
    ctrl.approve(0)
    monkeypatch.setattr(jc_mod, "write_pdf",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("USB desconectado")))
    ctrl.export(None, tmp_path / "out", today=TODAY)
    assert ctrl.items[0].status == ItemStatus.ERROR
    ctrl.set_mode(FitMode.COVER)
    assert ctrl.items[0].status == ItemStatus.READY
    assert ctrl.items[0].error is None
    ctrl.approve(0)
    assert ctrl.items[0].status == ItemStatus.APPROVED


# Importante 4: un fallo de análisis deja el ítem en ERROR con mensaje
def test_analysis_failure_marks_error(ctrl, make_image, tmp_path):
    good = make_image("ok.jpg", size=(800, 1200))
    truncated = tmp_path / "cortada.jpg"
    truncated.write_bytes(good.read_bytes()[:3000])
    ctrl.add_paths([truncated])
    assert ctrl.items[0].info is not None
    with pytest.raises(Exception):  # noqa: B017
        ctrl.analyze(0)
    assert ctrl.items[0].status == ItemStatus.ERROR
    assert "cortada.jpg" in ctrl.items[0].error
    assert ctrl.approve_all() == []
    assert ctrl.items[0].status == ItemStatus.ERROR


# Importante 5: calidad JPEG y artefactos medidos sobre el original, no el proxy
def test_large_low_quality_jpeg_flagged(tmp_path):
    p = tmp_path / "grande.jpg"
    Image.fromarray(texture_array((3000, 2000)), "RGB").save(p, "JPEG", quality=15)
    info = probe(p)
    d = analyze(info, load_proxy(p), 300)
    assert d.jpeg_quality is not None and d.jpeg_quality <= 25
    assert "Artefactos de compresión JPEG." in d.warnings


# Importante 6: versión del PDF acorde a SMask y PrintScaling
def test_pdf_version_at_least_1_6(make_image, tmp_path):
    src = make_image("a.jpg")
    info = probe(src)
    write_pdf(info, plan(info, PrintSpec(D(100), D(100)), FitMode.CONTAIN), tmp_path / "a.pdf")
    head = (tmp_path / "a.pdf").read_bytes()[:8]
    assert head >= b"%PDF-1.6"
    assert isinstance(io.BytesIO, type)
