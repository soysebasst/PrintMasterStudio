"""Controlador de un trabajo: cola de imágenes, formato, diagnóstico, aprobación y exportación.

No depende de Qt: la interfaz lo usa y lo ejecuta en hilos de fondo.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from printmaster.core.color import edge_color, flatten_alpha
from printmaster.core.enhance.enhancer import (
    EnhanceCancelled,
    EnhanceError,
    Enhancer,
    EnhanceResult,
    choose_model,
    passes_needed,
)
from printmaster.core.enhance.gemini_web import ENGINE_GEMINI, aspect_mismatch
from printmaster.core.image_analyzer import Diagnosis, rerate
from printmaster.core.image_analyzer import analyze as analyze_image
from printmaster.core.image_loader import (
    ImageLoadError,
    collect_images,
    load_proxy,
    load_rgb,
    probe,
)
from printmaster.core.layout import page_size_mm
from printmaster.core.layout import plan as make_plan
from printmaster.core.naming import NamingOptions, output_path, unique_path
from printmaster.core.pdf_writer import ExportOptions, PdfExportError, write_pdf
from printmaster.core.pricing import suggest_price
from printmaster.domain.models import (
    Background,
    BackgroundKind,
    CropOffset,
    CropRect,
    EnhanceChoice,
    FitMode,
    ImageInfo,
    ItemStatus,
    PrintSpec,
    RenderPlan,
)
from printmaster.domain.quality import QualityLevel, classify
from printmaster.infra import paths
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import PrinterProfile, ValidationIssue, validate

log = logging.getLogger("printmaster")

_LOW_LEVELS = (QualityLevel.BAJA, QualityLevel.MUY_BAJA)
# Errores que afectan a todo el lote (el ancho); los de largo dependen de cada imagen.
GLOBAL_ERROR_CODES = {"invalid", "too_wide"}


@dataclass
class JobItem:
    path: Path
    info: ImageInfo | None = None
    status: ItemStatus = ItemStatus.PENDING
    diagnosis: Diagnosis | None = None
    crop: CropOffset = CropOffset()
    region: CropRect = CropRect()  # recorte manual (fracciones de la imagen)
    duplicate_of: int | None = None
    error: str | None = None
    output: Path | None = None
    enhance_choice: EnhanceChoice = EnhanceChoice.AUTO
    enhanced: EnhanceResult | None = None
    enhanced_info: ImageInfo | None = None
    enhancing: bool = False
    enhance_gen: int = 0  # sube con cada mejora externa: una mejora local vieja no la pisa
    original_diagnosis: Diagnosis | None = None
    enhanced_diagnosis: Diagnosis | None = None

    @property
    def uses_enhanced(self) -> bool:
        return self.enhanced_info is not None and self.enhance_choice != EnhanceChoice.OFF


@dataclass(frozen=True)
class JobParams:
    """Parámetros congelados al iniciar una exportación."""

    spec: PrintSpec
    mode: FitMode
    background: Background
    naming: NamingOptions
    export_options: ExportOptions
    length_step_mm: int = 50


@dataclass(frozen=True)
class AttachResult:
    result: EnhanceResult
    aspect_warning: bool


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
        self.spec = PrintSpec(Decimal(settings.roll_width_mm), Decimal(900),
                              ppi=settings.default_ppi,
                              orientation=settings.default_orientation)
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
        """Tras un cambio de parámetros: quita aprobaciones, recupera ítems que fallaron al
        exportar y recalifica al instante con el PPI efectivo nuevo (sin decodificar)."""
        targets = list(range(len(self.items)) if indices is None else indices)
        for i in targets:
            item = self.items[i]
            if item.status in (ItemStatus.APPROVED, ItemStatus.EXPORTED):
                item.status = ItemStatus.READY
            elif (item.status == ItemStatus.ERROR and item.info is not None
                  and item.diagnosis is not None):
                item.status = ItemStatus.READY
                item.error = None
            self._rerate(i)

    def _rerate(self, i: int) -> None:
        item = self.items[i]
        base = item.enhanced_diagnosis if item.uses_enhanced else item.original_diagnosis
        base = base or item.diagnosis
        if item.info is None or base is None:
            return
        # El PPI efectivo no depende del fondo: se planifica con fondo blanco para no
        # decodificar la imagen (el color de borde requiere leerla).
        p = make_plan(self.source_info(i), self.spec, self.mode, Background(), item.crop,
                      self.settings.length_step_mm, self._aspect(i), item.region)
        item.diagnosis = rerate(base, p.effective_ppi)

    def _aspect(self, i: int) -> tuple[int, int] | None:
        info = self.items[i].info
        return (info.width_px, info.height_px) if info is not None else None

    def source_info(self, i: int) -> ImageInfo:
        """Imagen que realmente se imprime: la mejorada si existe y no se desactivó."""
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        return item.enhanced_info if item.uses_enhanced else item.info  # type: ignore[return-value]

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

    def set_region(self, i: int, region: CropRect) -> None:
        """Recorte manual: cambia el largo automático, el precio y el PPI efectivo."""
        item = self.items[i]
        if region != item.region:
            item.region = region
            item.crop = CropOffset()  # el desplazamiento de «Recortar» era de la zona anterior
            self._revoke_approvals([i])

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

    def issues(self, i: int | None = None, spec: PrintSpec | None = None) -> list[ValidationIssue]:
        base = spec or self.spec
        idx = i if i is not None else next(
            (k for k, it in enumerate(self.items) if it.info is not None), None)
        if idx is None or self.items[idx].info is None:
            return validate(base, self.profile)
        return validate(self._page_spec(idx, base, self.mode, self.settings.length_step_mm),
                        self.profile)

    def _page_spec(self, i: int, spec: PrintSpec, mode: FitMode, step: int) -> PrintSpec:
        """Formato de página ya resuelto para el ítem (largo automático incluido)."""
        w, h = page_size_mm(self.source_info(i), spec, mode, step, self._aspect(i),
                            self.items[i].region)
        return replace(spec, width_mm=w, height_mm=h)

    def page_size_for(self, i: int) -> tuple[Decimal, Decimal]:
        return page_size_mm(self.source_info(i), self.spec, self.mode,
                            self.settings.length_step_mm, self._aspect(i), self.items[i].region)

    def has_errors(self, i: int) -> bool:
        return any(x.level == "error" for x in self.issues(i))

    def exportable_indices(self) -> list[int]:
        return [i for i, it in enumerate(self.items)
                if it.status == ItemStatus.APPROVED and not self.has_errors(i)]

    def price_for(self, i: int) -> int | None:
        if self.items[i].info is None or self.has_errors(i):
            return None
        w, h = self.page_size_for(i)
        return suggest_price(w, h, self.settings.pricing())

    def total_price(self, indices: Iterable[int] | None = None) -> tuple[int, int]:
        targets = range(len(self.items)) if indices is None else indices
        count = total = 0
        for i in targets:
            item = self.items[i]
            if item.info is None or item.status == ItemStatus.ERROR or self.has_errors(i):
                continue
            count += 1
            total += self.price_for(i) or 0
        return count, total

    def _resolved_background(self, item: JobItem, bg: Background | None = None) -> Background:
        bg = bg if bg is not None else self.background
        if bg.kind != BackgroundKind.EDGE_COLOR:
            return bg
        if item.path not in self._edge_cache:
            self._edge_cache[item.path] = edge_color(load_proxy(item.path, 512))
        return replace(bg, kind=BackgroundKind.COLOR, color=self._edge_cache[item.path])

    def current_params(self) -> JobParams:
        return JobParams(self.spec, self.mode, self.background, self.naming,
                         self.export_options, self.settings.length_step_mm)

    def plan_for(self, i: int, params: JobParams | None = None,
                 crop: CropOffset | None = None, region: CropRect | None = None) -> RenderPlan:
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        params = params or self.current_params()
        bg = self._resolved_background(item, params.background)
        return make_plan(self.source_info(i), params.spec, params.mode, bg,
                         crop if crop is not None else item.crop, params.length_step_mm,
                         self._aspect(i), region if region is not None else item.region)

    # --- diagnóstico y aprobación ---------------------------------------------------
    def analyze(self, i: int) -> Diagnosis:
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        try:
            proxy = load_proxy(item.path)
        except ImageLoadError as exc:
            item.status = ItemStatus.ERROR
            item.error = str(exc)
            log.warning("%s", exc)
            raise
        orig_ppi = make_plan(item.info, self.spec, self.mode, Background(), item.crop,
                             self.settings.length_step_mm, region=item.region).effective_ppi
        item.original_diagnosis = analyze_image(item.info, proxy, orig_ppi)
        item.diagnosis = item.original_diagnosis
        # Los parámetros pudieron cambiar durante el análisis: calificar con los actuales.
        self._rerate(i)
        diag = item.diagnosis
        if item.status in (ItemStatus.PENDING, ItemStatus.ANALYZED, ItemStatus.READY,
                           ItemStatus.ERROR):
            item.status = ItemStatus.ANALYZED
            item.status = ItemStatus.READY
            item.error = None
        return diag

    # --- mejora con IA --------------------------------------------------------------
    def _original_ppi(self, i: int) -> float:
        item = self.items[i]
        assert item.info is not None
        return make_plan(item.info, self.spec, self.mode, Background(), item.crop,
                         self.settings.length_step_mm, region=item.region).effective_ppi

    def needs_enhancement(self, i: int) -> int:
        """Pasadas ×4 necesarias (0 = no mejorar)."""
        item = self.items[i]
        if item.info is None or item.enhance_choice == EnhanceChoice.OFF or item.uses_enhanced:
            return 0
        target = self.settings.enhance_target_ppi
        ppi = self._original_ppi(i)
        if item.enhance_choice == EnhanceChoice.ON:
            return max(1, passes_needed(ppi, target))
        if not self.settings.enhance_enabled or item.original_diagnosis is None:
            return 0
        if classify(ppi) not in _LOW_LEVELS:
            return 0
        return passes_needed(ppi, target)

    def set_enhance_choice(self, i: int, choice: EnhanceChoice) -> None:
        item = self.items[i]
        if choice != item.enhance_choice:
            item.enhance_choice = choice
            self._revoke_approvals([i])

    def enhance(self, i: int, enhancer: Enhancer, cancel: threading.Event | None = None,
                progress: Callable[[int, int], None] | None = None) -> EnhanceResult:
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        passes = self.needs_enhancement(i)
        if passes == 0:
            raise ValueError("Esta imagen no necesita mejora.")
        info = item.info
        gen = item.enhance_gen
        item.enhancing = True
        result: EnhanceResult | None = None
        try:
            model = choose_model(load_proxy(item.path, 512))
            result = enhancer.enhance(item.path, info.sha256, passes, model, cancel, progress)
            einfo = probe(result.path)
            plan_e = make_plan(einfo, self.spec, self.mode, Background(), item.crop,
                               self.settings.length_step_mm, (info.width_px, info.height_px),
                               item.region)
            if item.enhance_gen != gen:
                # Mientras tanto se adjuntó una mejora externa (Gemini): no se sobrescribe.
                return item.enhanced  # type: ignore[return-value]
            # Métricas de contenido (nitidez, ruido, compresión) del original; PPI de la
            # mejorada. Medir "desenfoque" sobre píxeles interpolados no es informativo.
            base = item.original_diagnosis or item.diagnosis
            if base is None:
                base = self.analyze(next(k for k, it in enumerate(self.items) if it is item))
            item.enhanced_diagnosis = rerate(base, plan_e.effective_ppi)
            item.enhanced, item.enhanced_info = result, einfo
            item.error = None
        except MemoryError as exc:
            item.error = "Memoria insuficiente para mejorar esta imagen; se usará la original."
            log.warning("Mejora sin memoria para %s", item.path.name)
            raise EnhanceError(item.error) from exc
        except (EnhanceError, ImageLoadError, OSError) as exc:
            item.error = str(exc)
            log.warning("Mejora fallida para %s: %s", item.path.name, exc)
            if isinstance(exc, EnhanceError):
                raise
            raise EnhanceError(str(exc)) from exc
        finally:
            item.enhancing = False
        # La mejora pudo tardar minutos: la cola pudo cambiar. Se busca por identidad.
        idx = next((k for k, it in enumerate(self.items) if it is item), None)
        if idx is not None:
            self._revoke_approvals([idx])
        return result

    def attach_external(self, i: int, path: Path, enhancer: Enhancer | None = None,
                        cancel: threading.Event | None = None) -> AttachResult:
        """Usa como versión mejorada una imagen externa (p. ej. descargada de Gemini web).

        El archivo soltado no se modifica: se copia como PNG a la caché. El largo y el precio
        siguen saliendo de la proporción del original.
        """
        item = self.items[i]
        if item.info is None:
            raise ValueError(item.error or "La imagen no se pudo leer.")
        orig = item.info
        dropped = probe(Path(path))  # ImageLoadError si no es una imagen válida
        img, _ = load_rgb(dropped.path)
        cache = paths.data_dir() / "cache" / "external"
        cache.mkdir(parents=True, exist_ok=True)
        copy = cache / f"{orig.sha256}_{dropped.sha256}.png"
        if not copy.exists():
            tmp = copy.with_name(copy.name + ".tmp")
            flatten_alpha(img).convert("RGB").save(tmp, "PNG")
            os.replace(tmp, copy)
        ext_info = probe(copy)
        warning = aspect_mismatch((orig.width_px, orig.height_px),
                                  (ext_info.width_px, ext_info.height_px))
        aspect = (orig.width_px, orig.height_px)

        def ppi_of(info: ImageInfo) -> float:
            return make_plan(info, self.spec, self.mode, Background(), item.crop,
                             self.settings.length_step_mm, aspect, item.region).effective_ppi

        result = EnhanceResult(copy, "gemini-web", 0, ENGINE_GEMINI)
        final_info = ext_info
        ppi = ppi_of(ext_info)
        target = self.settings.enhance_target_ppi
        item.enhance_gen += 1  # cualquier mejora local en curso queda descartada
        if ppi < target and enhancer is not None:
            passes = passes_needed(ppi, target)
            model = choose_model(load_proxy(copy, 512))
            try:
                local = enhancer.enhance(copy, ext_info.sha256, passes, model, cancel)
            except EnhanceCancelled:
                local = None  # se usa la de Gemini sin el pase local
            if local is not None:
                final_info = probe(local.path)
                result = EnhanceResult(local.path, model, passes,
                                       f"{ENGINE_GEMINI} + {local.engine}")
                ppi = ppi_of(final_info)
        if item.original_diagnosis is None:
            idx_now = next((k for k, it in enumerate(self.items) if it is item), None)
            if idx_now is not None:
                self.analyze(idx_now)
        base = item.original_diagnosis or item.diagnosis
        item.enhanced, item.enhanced_info = result, final_info
        if base is not None:
            item.enhanced_diagnosis = rerate(base, ppi)
        if item.enhance_choice == EnhanceChoice.OFF:
            item.enhance_choice = EnhanceChoice.AUTO
        item.error = None
        idx = next((k for k, it in enumerate(self.items) if it is item), None)
        if idx is not None:
            self._revoke_approvals([idx])
        return AttachResult(result, warning)

    def approve(self, i: int) -> None:
        item = self.items[i]
        if item.status in (ItemStatus.READY, ItemStatus.EXPORTED, ItemStatus.APPROVED):
            item.status = ItemStatus.APPROVED

    def approve_all(self) -> list[int]:
        skipped: list[int] = []
        for i, item in enumerate(self.items):
            if item.status != ItemStatus.READY:
                continue
            if item.diagnosis is None or (item.diagnosis.level in _LOW_LEVELS
                                          and not item.uses_enhanced):
                # una mejora de Gemini ya es la mejor versión disponible: se aprueba
                skipped.append(i)
                continue
            item.status = ItemStatus.APPROVED
        return skipped

    # --- exportación ----------------------------------------------------------------
    def _index_of(self, item: JobItem, hint: int) -> int:
        if 0 <= hint < len(self.items) and self.items[hint] is item:
            return hint
        for j, it in enumerate(self.items):
            if it is item:
                return j
        return hint

    def export(
        self,
        indices: Sequence[int] | None,
        out_dir: Path,
        progress: Callable[[int, int], None] | None = None,
        today: date | None = None,
    ) -> list[ExportResult]:
        params = self.current_params()  # congelados: cambios posteriores no afectan el lote
        errors = [x for x in self.issues(spec=params.spec)
                  if x.level == "error" and x.code in GLOBAL_ERROR_CODES]
        if errors:
            raise ValueError(errors[0].message)
        today = today or date.today()
        targets = list(indices) if indices is not None else [
            i for i, it in enumerate(self.items) if it.status == ItemStatus.APPROVED]
        jobs = [(i, self.items[i], self.items[i].crop, self.items[i].region) for i in targets]
        results: list[ExportResult] = []
        total = len(jobs)
        for k, (i, item, crop, region) in enumerate(jobs):
            i = self._index_of(item, i)
            try:
                if item.info is None:
                    raise ValueError(item.error or "La imagen no se pudo leer.")
                own_errors = [x for x in validate(
                    self._page_spec(i, params.spec, params.mode, params.length_step_mm),
                    self.profile) if x.level == "error"]
                if own_errors:
                    raise ValueError(own_errors[0].message)
                out = unique_path(output_path(out_dir, k, item.path, params.naming, today))
                write_pdf(self.source_info(i), self.plan_for(i, params, crop, region), out,
                          params.export_options)
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
