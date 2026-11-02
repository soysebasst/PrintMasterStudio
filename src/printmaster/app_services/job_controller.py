"""Controlador de un trabajo: cola de imágenes, formato, diagnóstico, aprobación y exportación.

No depende de Qt: la interfaz lo usa y lo ejecuta en hilos de fondo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from printmaster.core.color import edge_color
from printmaster.core.image_analyzer import Diagnosis
from printmaster.core.image_analyzer import analyze as analyze_image
from printmaster.core.image_loader import ImageLoadError, collect_images, load_proxy, probe
from printmaster.core.layout import plan as make_plan
from printmaster.core.naming import NamingOptions, output_path, unique_path
from printmaster.core.pdf_writer import ExportOptions, PdfExportError, write_pdf
from printmaster.domain.models import (
    Background,
    BackgroundKind,
    CropOffset,
    FitMode,
    ImageInfo,
    ItemStatus,
    PrintSpec,
    RenderPlan,
)
from printmaster.domain.quality import QualityLevel
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import PrinterProfile, ValidationIssue, validate

log = logging.getLogger("printmaster")

_LOW_LEVELS = (QualityLevel.BAJA, QualityLevel.MUY_BAJA)


@dataclass
class JobItem:
    path: Path
    info: ImageInfo | None = None
    status: ItemStatus = ItemStatus.PENDING
    diagnosis: Diagnosis | None = None
    crop: CropOffset = CropOffset()
    duplicate_of: int | None = None
    error: str | None = None
    output: Path | None = None


@dataclass
class ExportResult:
    index: int
    ok: bool
    output: Path | None
    error: str | None


class JobController:
    def __init__(self, settings: Settings, profile: PrinterProfile) -> None:
        self.settings = settings
        self.profile = profile
        self.items: list[JobItem] = []
        self.spec = PrintSpec(Decimal(600), Decimal(900), ppi=settings.default_ppi)
        self.mode: FitMode = settings.default_mode
        self.background = Background()
        self.export_options = ExportOptions()
        self.naming = NamingOptions(prefix=settings.naming_prefix, digits=settings.naming_digits,
                                    by_date=settings.naming_by_date)
        self._edge_cache: dict[Path, tuple[int, int, int]] = {}

    # --- cola -------------------------------------------------------------------------
    def add_paths(self, paths: Iterable[Path]) -> list[int]:
        new: list[int] = []
        for path in collect_images(paths):
            item = JobItem(path=path)
            try:
                item.info = probe(path)
            except ImageLoadError as exc:
                item.status = ItemStatus.ERROR
                item.error = str(exc)
                log.warning("%s", exc)
            else:
                for j, other in enumerate(self.items):
                    if other.info is not None and other.info.sha256 == item.info.sha256:
                        item.duplicate_of = j
                        break
            self.items.append(item)
            new.append(len(self.items) - 1)
        return new

    def remove(self, indices: Iterable[int]) -> None:
        drop = set(indices)
        self.items = [it for i, it in enumerate(self.items) if i not in drop]
        self._recompute_duplicates()

    def move(self, src: int, dst: int) -> None:
        item = self.items.pop(src)
        self.items.insert(dst, item)
        self._recompute_duplicates()

    def _recompute_duplicates(self) -> None:
        seen: dict[str, int] = {}
        for i, it in enumerate(self.items):
            it.duplicate_of = None
            if it.info is None:
                continue
            if it.info.sha256 in seen:
                it.duplicate_of = seen[it.info.sha256]
            else:
                seen[it.info.sha256] = i

    # --- parámetros -----------------------------------------------------------------
    def _revoke_approvals(self, indices: Iterable[int] | None = None) -> None:
        targets = range(len(self.items)) if indices is None else indices
        for i in targets:
            if self.items[i].status in (ItemStatus.APPROVED, ItemStatus.EXPORTED):
                self.items[i].status = ItemStatus.READY

    def set_spec(self, spec: PrintSpec) -> None:
        if spec != self.spec:
            self.spec = spec
            self._revoke_approvals()

    def set_mode(self, mode: FitMode) -> None:
        if mode != self.mode:
            self.mode = mode
            self._revoke_approvals()

    def set_background(self, bg: Background) -> None:
        if bg != self.background:
            self.background = bg
            self._revoke_approvals()

    def set_crop(self, i: int, crop: CropOffset) -> None:
        if crop != self.items[i].crop:
            self.items[i].crop = crop
            self._revoke_approvals([i])

    # --- consultas ------------------------------------------------------------------
    def resolved_spec(self, i: int | None = None) -> PrintSpec:
        idx = i if i is not None else next(
            (k for k, it in enumerate(self.items) if it.info is not None), None)
        if idx is None or self.items[idx].info is None:
            return self.spec
        info = self.items[idx].info
        return self.spec.resolved_for(info.width_px, info.height_px)

    def issues(self, i: int | None = None) -> list[ValidationIssue]:
        return validate(self.resolved_spec(i), self.profile)

    def _resolved_background(self, item: JobItem) -> Background:
        bg = self.background
        if bg.kind != BackgroundKind.EDGE_COLOR:
            return bg
        if item.path not in self._edge_cache:
            self._edge_cache[item.path] = edge_color(load_proxy(item.path, 512))
        return replace(bg, kind=BackgroundKind.COLOR, color=self._edge_cache[item.path])

    def plan_for(self, i: int) -> RenderPlan:
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        return make_plan(item.info, self.spec, self.mode, self._resolved_background(item),
                         item.crop)

    # --- diagnóstico y aprobación ---------------------------------------------------
    def analyze(self, i: int) -> Diagnosis:
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        p = self.plan_for(i)
        diag = analyze_image(item.info, load_proxy(item.path), p.effective_ppi)
        item.diagnosis = diag
        if item.status in (ItemStatus.PENDING, ItemStatus.ANALYZED, ItemStatus.READY):
            item.status = ItemStatus.ANALYZED
            item.status = ItemStatus.READY
        return diag

    def approve(self, i: int) -> None:
        item = self.items[i]
        if item.status in (ItemStatus.READY, ItemStatus.EXPORTED, ItemStatus.APPROVED):
            item.status = ItemStatus.APPROVED

    def approve_all(self) -> list[int]:
        skipped: list[int] = []
        for i, item in enumerate(self.items):
            if item.status != ItemStatus.READY:
                continue
            if item.diagnosis is None or item.diagnosis.level in _LOW_LEVELS:
                skipped.append(i)
                continue
            item.status = ItemStatus.APPROVED
        return skipped

    # --- exportación ----------------------------------------------------------------
    def export(
        self,
        indices: Sequence[int] | None,
        out_dir: Path,
        progress: Callable[[int, int], None] | None = None,
        today: date | None = None,
    ) -> list[ExportResult]:
        errors = [x for x in self.issues() if x.level == "error"]
        if errors:
            raise ValueError(errors[0].message)
        today = today or date.today()
        targets = list(indices) if indices is not None else [
            i for i, it in enumerate(self.items) if it.status == ItemStatus.APPROVED]
        results: list[ExportResult] = []
        total = len(targets)
        for k, i in enumerate(targets):
            item = self.items[i]
            try:
                if item.info is None:
                    raise ValueError(item.error or "La imagen no se pudo leer.")
                own_errors = [x for x in self.issues(i) if x.level == "error"]
                if own_errors:
                    raise ValueError(own_errors[0].message)
                out = unique_path(output_path(out_dir, k, item.path, self.naming, today))
                write_pdf(item.info, self.plan_for(i), out, self.export_options)
            except (PdfExportError, ImageLoadError, ValueError, OSError) as exc:
                item.status = ItemStatus.ERROR
                item.error = str(exc)
                log.error("Error exportando %s: %s", item.path.name, exc)
                results.append(ExportResult(i, False, None, str(exc)))
            else:
                item.status = ItemStatus.EXPORTED
                item.output = out
                item.error = None
                results.append(ExportResult(i, True, out, None))
            if progress is not None:
                progress(k + 1, total)
        return results
