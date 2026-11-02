import hashlib
from datetime import date
from decimal import Decimal as D

import pytest
from pypdf import PdfReader

from printmaster.app_services import job_controller as jc_mod
from printmaster.app_services.job_controller import JobController
from printmaster.domain.models import (
    Background,
    BackgroundKind,
    FitMode,
    ItemStatus,
    Orientation,
    PrintSpec,
)
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile

TODAY = date(2026, 11, 2)


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    c = JobController(Settings(output_dir=tmp_path / "out"), load_profile())
    c.set_spec(PrintSpec(D(100), D(150), ppi=200, orientation=Orientation.PORTRAIT))
    return c


@pytest.fixture
def batch(make_image, tmp_path):
    folder = tmp_path / "in"
    good = [make_image(f"img{i}.jpg", size=(800, 1200), seed=i, folder=folder) for i in range(4)]
    low = make_image("pequeña.jpg", size=(60, 90), seed=9, folder=folder)
    bad = folder / "roto.jpg"
    bad.write_bytes(b"basura" * 50)
    dup = folder / "zcopia.jpg"
    dup.write_bytes(good[0].read_bytes())
    return folder, good, low, bad, dup


def test_add_paths(ctrl, batch):
    folder, *_ = batch
    new = ctrl.add_paths([folder])
    assert len(new) == 7
    names = [it.path.name for it in ctrl.items]
    bad = ctrl.items[names.index("roto.jpg")]
    assert bad.status == ItemStatus.ERROR and "roto.jpg" in bad.error
    assert ctrl.items[names.index("zcopia.jpg")].duplicate_of == names.index("img0.jpg")


def analyze_all(ctrl):
    for i, it in enumerate(ctrl.items):
        if it.status != ItemStatus.ERROR:
            ctrl.analyze(i)


def test_approve_all_skips_low_res(ctrl, batch):
    ctrl.add_paths([batch[0]])
    analyze_all(ctrl)
    skipped = ctrl.approve_all()
    names = [ctrl.items[i].path.name for i in skipped]
    assert names == ["pequeña.jpg"]
    approved = [it for it in ctrl.items if it.status == ItemStatus.APPROVED]
    assert len(approved) == 5  # 4 buenas + duplicado


def test_export(ctrl, batch, tmp_path):
    ctrl.add_paths(batch[1])
    analyze_all(ctrl)
    ctrl.approve_all()
    calls = []
    results = ctrl.export(None, tmp_path / "out", lambda k, n: calls.append((k, n)), TODAY)
    assert all(r.ok for r in results) and len(results) == 4
    folder = tmp_path / "out" / "2026-11-02"
    assert sorted(p.name for p in folder.glob("*.pdf")) == [
        "Cliente_001.pdf", "Cliente_002.pdf", "Cliente_003.pdf", "Cliente_004.pdf"]
    assert calls == [(1, 4), (2, 4), (3, 4), (4, 4)]
    box = PdfReader(str(folder / "Cliente_001.pdf")).pages[0].mediabox
    assert abs(float(box.width) - 283.4646) < 0.01
    assert all(it.status == ItemStatus.EXPORTED and it.output for it in ctrl.items)


def test_one_failure_does_not_stop_batch(ctrl, batch, tmp_path, monkeypatch):
    ctrl.add_paths(batch[1])
    analyze_all(ctrl)
    ctrl.approve_all()
    real = jc_mod.write_pdf

    def flaky(info, plan, out, options):
        if info.path.name == "img2.jpg":
            raise jc_mod.PdfExportError("fallo simulado")
        return real(info, plan, out, options)

    monkeypatch.setattr(jc_mod, "write_pdf", flaky)
    results = ctrl.export(None, tmp_path / "out", today=TODAY)
    assert [r.ok for r in results] == [True, True, False, True]
    assert ctrl.items[2].status == ItemStatus.ERROR
    assert "fallo simulado" in ctrl.items[2].error


def test_export_twice_never_overwrites(ctrl, batch, tmp_path):
    ctrl.add_paths(batch[1][:1])
    analyze_all(ctrl)
    ctrl.approve_all()
    ctrl.export(None, tmp_path / "out", today=TODAY)
    ctrl.export([0], tmp_path / "out", today=TODAY)
    names = sorted(p.name for p in (tmp_path / "out" / "2026-11-02").glob("*.pdf"))
    assert names == ["Cliente_001.pdf", "Cliente_001_2.pdf"]


def test_originals_untouched(ctrl, batch, tmp_path):
    good = batch[1]
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in good]
    ctrl.add_paths(good)
    analyze_all(ctrl)
    ctrl.approve_all()
    ctrl.export(None, tmp_path / "out", today=TODAY)
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in good] == before


def test_invalid_format_blocks_export(ctrl, batch, tmp_path):
    ctrl.add_paths(batch[1][:1])
    ctrl.set_spec(PrintSpec(D(700), D(700)))
    with pytest.raises(ValueError, match="Ningún lado"):
        ctrl.export([0], tmp_path / "out", today=TODAY)


def test_move_and_remove(ctrl, batch):
    ctrl.add_paths(batch[1])
    first = ctrl.items[0].path
    ctrl.move(0, 2)
    assert ctrl.items[2].path == first
    ctrl.remove([0, 1])
    assert len(ctrl.items) == 2


def test_changes_revoke_approval(ctrl, batch):
    ctrl.add_paths(batch[1][:1])
    ctrl.analyze(0)
    ctrl.approve(0)
    ctrl.set_mode(FitMode.COVER)
    assert ctrl.items[0].status == ItemStatus.READY


def test_edge_color_resolved(ctrl, make_image):
    p = make_image("e.png", pattern="solid", color=(200, 10, 10), size=(100, 300))
    ctrl.add_paths([p])
    ctrl.set_mode(FitMode.FILL)
    ctrl.set_background(Background(BackgroundKind.EDGE_COLOR))
    plan = ctrl.plan_for(0)
    assert plan.background.kind == BackgroundKind.COLOR
    assert plan.background.color[0] > 180
