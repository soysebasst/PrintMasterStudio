"""Página "Nuevo trabajo": cola, vista previa, inspector, aprobación y exportación."""

from __future__ import annotations

import subprocess
import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from printmaster.app_services.job_controller import JobController, JobItem
from printmaster.core.enhance.enhancer import ENGINE_AI, Enhancer, EnhanceResult
from printmaster.core.enhance.gemini_web import GEMINI_URL, reveal_command
from printmaster.core.enhance.installer import find_engine
from printmaster.core.enhance.realesrgan import EnhanceCancelled
from printmaster.core.image_loader import load_proxy
from printmaster.core.pdf_writer import ExportOptions
from printmaster.core.pricing import format_cop
from printmaster.domain.models import FitMode, ItemStatus
from printmaster.infra import paths
from printmaster.infra.settings import FavoriteFormat, Settings
from printmaster.printers.profiles import PrinterProfile
from printmaster.ui.models.queue_model import QueueModel
from printmaster.ui.qt_images import pil_to_qimage
from printmaster.ui.widgets.inspector import Inspector
from printmaster.ui.widgets.preview_canvas import PreviewCanvas
from printmaster.ui.widgets.quality_panel import QualityPanel
from printmaster.ui.widgets.queue_view import QueueView
from printmaster.ui.workers import run_async

PREVIEW_SIDE = 1600
MAX_BACKGROUND_THREADS = 2  # especificación R5: como máximo 2 imágenes decodificándose a la vez
PREVIEW_CACHE = 8
STEPS = ["① Cargar", "② Formato", "③ Revisar", "④ Exportar"]


class _ProgressBridge(QObject):
    progress = Signal(int, int)


class JobPage(QWidget):
    def __init__(self, settings: Settings, profile: PrinterProfile,
                 enhancer: Enhancer | None = None, parent=None) -> None:
        super().__init__(parent)
        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(min(pool.maxThreadCount(), MAX_BACKGROUND_THREADS))
        self.settings = settings
        self.profile = profile
        self.controller = JobController(settings, profile)
        self.model = QueueModel(self.controller)
        self._previews: OrderedDict[Path, QImage] = OrderedDict()
        self.enhancer = enhancer or Enhancer(find_engine(), self._cache_dir())
        self._enhance_queue: list[JobItem] = []
        self._skip_enhance: list[JobItem] = []  # canceladas o fallidas: no reintentar solas
        self._enhancing: JobItem | None = None
        self._cancel_enhance = threading.Event()
        self._show_original = False
        self._gemini_hint: str | None = None
        self._exporting = False
        self._pending_settings: Settings | None = None
        self._bridge = _ProgressBridge()
        self._bridge.progress.connect(self._on_progress)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        self.steps_label = QLabel()
        self.steps_label.setObjectName("steps")
        self.steps_label.setTextFormat(Qt.RichText)
        root.addWidget(self.steps_label)

        splitter = QSplitter(Qt.Horizontal)
        self.queue = QueueView(self.model)
        self.queue.setMinimumWidth(240)
        splitter.addWidget(self.queue)

        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        self.canvas = PreviewCanvas()
        center_lay.addWidget(self.canvas, 1)
        zoom_row = QHBoxLayout()
        self.zoom_out_btn = QPushButton("−")
        self.fit_btn = QPushButton("Ajustar a la vista")
        self.zoom_in_btn = QPushButton("+")
        self.before_after_btn = QPushButton("Ver original")
        self.before_after_btn.setToolTip("Comparar la imagen original con la mejorada con IA")
        self.before_after_btn.setEnabled(False)
        for b in (self.zoom_out_btn, self.fit_btn, self.zoom_in_btn, self.before_after_btn):
            zoom_row.addWidget(b)
        zoom_row.addStretch(1)
        self.ppi_info = QLabel("")
        zoom_row.addWidget(self.ppi_info)
        center_lay.addLayout(zoom_row)
        splitter.addWidget(center)

        side = QWidget()
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        self.inspector = Inspector(settings)
        self.quality = QualityPanel()
        self.diagnosis = self.quality  # compatibilidad: show_diagnosis() / text()
        self.inspector.layout().insertWidget(self.inspector.quality_insert_index(), self.quality)
        self.quality.choice_row.addWidget(self.inspector.enhance_combo, 1)
        side_lay.addWidget(self.inspector)
        self.side_panel = side
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(side)
        scroll.setMinimumWidth(300)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 700, 330])
        root.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        bottom.addWidget(self.progress, 1)
        self.total_label = QLabel("")
        self.total_label.setObjectName("total_label")
        self.total_label.setStyleSheet("color:#7ee787; font-weight:bold; padding: 0 8px;")
        bottom.addWidget(self.total_label)
        self.cancel_enhance_btn = QPushButton("Cancelar mejora")
        self.cancel_enhance_btn.setVisible(False)
        bottom.addWidget(self.cancel_enhance_btn)
        self.approve_btn = QPushButton("Aprobar seleccionada")
        self.approve_all_btn = QPushButton("Aprobar todo")
        self.export_btn = QPushButton("Exportar PDF")
        self.export_btn.setProperty("primary", True)
        for b in (self.approve_btn, self.approve_all_btn, self.export_btn):
            bottom.addWidget(b)
        root.addLayout(bottom)

        # conexiones
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        self.fit_btn.clicked.connect(self.canvas.fit)
        self.before_after_btn.clicked.connect(self._toggle_before_after)
        self.cancel_enhance_btn.clicked.connect(self._cancel_enhancements)
        self.inspector.enhance_choice_changed.connect(self._on_enhance_choice)
        self.quality.gemini_btn.clicked.connect(self._on_gemini)
        self.quality.drop_zone.file_dropped.connect(self._on_external_dropped)
        self.queue.current_changed.connect(self._on_current_changed)
        self.queue.paths_added.connect(self._on_paths_added)
        self.model.rowsRemoved.connect(lambda *a: self._after_queue_change())
        self.model.rowsRemoved.connect(lambda *a: self._drop_removed_enhancements())
        self.model.rowsMoved.connect(lambda *a: self._after_queue_change())
        self.inspector.changed.connect(self._on_params_changed)
        self.canvas.crop_changed.connect(self._on_crop_changed)
        self.approve_btn.clicked.connect(self._approve_current)
        self.approve_all_btn.clicked.connect(self._approve_all)
        self.export_btn.clicked.connect(self._export)

        self.favorite_saved = self.inspector.favorite_saved
        self._apply_params()
        self._update_state()

    # --- integración con la ventana -------------------------------------------------
    @staticmethod
    def _cache_dir() -> Path:
        return paths.data_dir() / "cache" / "enhanced"

    def reload_engine(self) -> None:
        self.enhancer = Enhancer(find_engine(), self._cache_dir())

    def apply_favorite(self, fav: FavoriteFormat) -> None:
        if self._exporting:
            return
        self.inspector.apply_favorite(fav)

    def set_settings(self, settings: Settings) -> None:
        if self._exporting:
            self._pending_settings = settings
            return
        self.settings = settings
        self.controller.settings = settings
        self.controller.naming = type(self.controller.naming)(
            prefix=settings.naming_prefix, digits=settings.naming_digits,
            by_date=settings.naming_by_date)
        self.inspector.set_favorites(settings.favorites)

    # --- mensajes (sobrescribibles en pruebas) --------------------------------------
    def _info(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def _export_finished(self, ok: int, err: int, folder: Path) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Exportación terminada")
        box.setText(f"{ok} PDF generados, {err} con error.")
        open_btn = box.addButton("Abrir carpeta", QMessageBox.ActionRole)
        box.addButton("Cerrar", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # --- estado ---------------------------------------------------------------------
    def _current_index(self) -> int:
        row = self.queue.current_row()
        return row if 0 <= row < len(self.controller.items) else -1

    def _update_state(self) -> None:
        items = self.controller.items
        cur_idx = self._current_index()
        issues = self.controller.issues(cur_idx if cur_idx >= 0 else None)
        self.inspector.show_issues(issues)
        approved = any(it.status == ItemStatus.APPROVED for it in items)
        exportable = bool(self.controller.exportable_indices()) if items else False
        if approved:
            step = 3
        elif any(it.diagnosis is not None for it in items):
            step = 2
        elif items:
            step = 1
        else:
            step = 0
        parts = [f'<b style="color:#3d8bfd">{s}</b>' if i == step else s
                 for i, s in enumerate(STEPS)]
        self.steps_label.setText("  ─  ".join(parts))
        busy = self._exporting
        enhancing = self._enhancing is not None or bool(self._enhance_queue)
        self.export_btn.setEnabled(exportable and not busy and not enhancing)
        self.cancel_enhance_btn.setVisible(enhancing)
        count, total = self.controller.total_price()
        self.total_label.setText(
            f"{count} lámina{'s' if count != 1 else ''} · {format_cop(total)}" if count else "")
        self.approve_all_btn.setEnabled(bool(items) and not busy)
        cur = self._current_index()
        self.approve_btn.setEnabled(
            cur >= 0 and items[cur].status in (ItemStatus.READY, ItemStatus.EXPORTED)
            and not busy)
        self.before_after_btn.setEnabled(cur >= 0 and items[cur].uses_enhanced)
        if not self.before_after_btn.isEnabled():
            self._show_original = False
        self.before_after_btn.setText("Ver mejorada" if self._show_original else "Ver original")

    def _after_queue_change(self) -> None:
        self._update_state()
        self._on_current_changed(self._current_index())

    # --- análisis en segundo plano --------------------------------------------------
    def _analyze_item(self, item: JobItem) -> None:
        idx = self._row_of(item)
        if idx >= 0:
            self.controller.analyze(idx)

    def _schedule_analysis(self, items: list[JobItem]) -> None:
        for item in items:
            if item.info is None:
                continue
            run_async(self._analyze_item, item,
                      on_done=lambda _r, it=item: self._analysis_done(it),
                      on_failed=lambda _msg, it=item: self._analysis_done(it), owner=self)

    def _row_of(self, item: JobItem) -> int:
        for i, it in enumerate(self.controller.items):
            if it is item:
                return i
        return -1

    def _analysis_done(self, item: JobItem) -> None:
        row = self._row_of(item)
        if row < 0:
            return
        self._maybe_enqueue(item)
        self.model.refresh(row)
        if row == self._current_index():
            self._show_diagnosis(row)
        self._update_state()

    def _on_paths_added(self, new: list[int]) -> None:
        self._schedule_analysis([self.controller.items[i] for i in new])
        self._update_state()

    # --- parámetros -----------------------------------------------------------------
    def _apply_params(self) -> None:
        self.controller.set_spec(self.inspector.spec())
        self.controller.set_mode(self.inspector.mode())
        self.controller.set_background(self.inspector.background())
        self.controller.export_options = ExportOptions(lossless=self.inspector.lossless())

    def _on_params_changed(self) -> None:
        if self._exporting:
            return
        # El controlador recalifica al instante con el PPI nuevo (sin volver a decodificar).
        self._apply_params()
        self.model.refresh()
        self._redraw_current()
        cur = self._current_index()
        if cur >= 0:
            self._show_diagnosis(cur)
        for item in list(self.controller.items):
            self._maybe_enqueue(item)
        self._update_state()

    def _on_crop_changed(self, crop) -> None:
        if self._exporting:
            return
        i = self._current_index()
        if i >= 0:
            self.controller.set_crop(i, crop)
            self.model.refresh(i)
            self._redraw_current()
            self._update_state()

    # --- vista previa ---------------------------------------------------------------
    def _on_current_changed(self, row: int) -> None:
        if not (0 <= row < len(self.controller.items)):
            self.canvas.clear()
            self.diagnosis.show_diagnosis(None, None, error="Sin imagen seleccionada.")
            self.ppi_info.setText("")
            self._update_state()
            return
        self._show_original = False
        self.inspector.set_enhance_choice(self.controller.items[row].enhance_choice)
        self._show_diagnosis(row)
        self._redraw_current()
        self._update_state()

    def _show_diagnosis(self, row: int) -> None:
        item = self.controller.items[row]
        downsample = None
        if item.info is not None:
            try:
                p = self.controller.plan_for(row)
            except Exception:  # noqa: BLE001
                p = None
            if p is not None and p.output_px is not None and not p.compose_page:
                downsample = self.controller.spec.ppi
        price = page = enhanced = None
        if item.info is not None:
            price = self.controller.price_for(row)
            page = self.controller.page_size_for(row)
            self.inspector.set_calculated_length(page[1])
            if item.uses_enhanced and item.enhanced is not None:
                enhanced = (item.enhanced_info, item.enhanced)
        self.diagnosis.show_diagnosis(item.diagnosis, item.info, downsample, item.error,
                                      price=price, page_mm=page, enhanced=enhanced,
                                      enhancing=item.enhancing)

    def _redraw_current(self) -> None:
        row = self._current_index()
        if row < 0:
            return
        item = self.controller.items[row]
        if item.info is None:
            self.canvas.clear()
            return
        path = self._preview_path(item)
        cached = self._previews.get(path)
        if cached is not None:
            self._draw(item, cached)
            return
        run_async(load_proxy, path, PREVIEW_SIDE,
                  on_done=lambda img, it=item, p=path: self._preview_loaded(it, img, p),
                  on_failed=lambda _m: None, owner=self)

    def _preview_path(self, item: JobItem) -> Path:
        if item.uses_enhanced and item.enhanced is not None and not self._show_original:
            return item.enhanced.path
        return item.path

    def _preview_loaded(self, item: JobItem, img, path: Path | None = None) -> None:
        qimg = pil_to_qimage(img)
        path = path or item.path
        self._previews[path] = qimg
        while len(self._previews) > PREVIEW_CACHE:
            self._previews.popitem(last=False)
        row = self._row_of(item)
        if row >= 0 and row == self._current_index() and path == self._preview_path(item):
            self._draw(item, qimg)

    def _draw(self, item: JobItem, qimg: QImage) -> None:
        row = self._row_of(item)
        if row < 0 or item.info is None:
            return
        try:
            plan = self.controller.plan_for(row)
        except Exception as exc:  # noqa: BLE001
            self.ppi_info.setText(str(exc))
            return
        src = self.controller.source_info(row)  # el plan está en píxeles de la fuente impresa
        self.canvas.show_plan(qimg, plan, FitMode(self.controller.mode), self.profile,
                              (src.width_px, src.height_px))
        self.ppi_info.setText(f"PPI efectivo: {plan.effective_ppi:.0f}")

    # --- aprobación y exportación ---------------------------------------------------
    def _approve_current(self) -> None:
        i = self._current_index()
        if i >= 0:
            self.controller.approve(i)
            self.model.refresh(i)
            self._update_state()

    def _approve_all(self) -> None:
        skipped = self.controller.approve_all()
        self.model.refresh()
        self._update_state()
        messages = []
        if skipped:
            messages.append(f"Se omitieron {len(skipped)} imágenes con baja resolución. "
                            "Revíselas y apruébelas una por una.")
        approved = [it for it in self.controller.items
                    if it.uses_enhanced and it.enhanced is not None
                    and it.status == ItemStatus.APPROVED]
        ai = sum(1 for it in approved if it.enhanced.engine == ENGINE_AI)
        basic = len(approved) - ai
        if ai:
            messages.append(f"Se mejoraron {ai} imágenes con IA: revíselas con "
                            "«Ver original / Ver mejorada».")
        if basic:
            messages.append(f"Se mejoraron {basic} imágenes con la mejora básica (sin IA): "
                            "revíselas con «Ver original / Ver mejorada».")
        if messages:
            self._info("Aprobación", "\n\n".join(messages))

    def _export(self) -> None:
        if self._exporting:
            return
        self._exporting = True
        self.progress.setValue(0)
        self._set_inputs_enabled(False)
        self._update_state()
        out_dir = Path(self.settings.output_dir)
        run_async(self.controller.export, None, out_dir,
                  lambda k, n: self._bridge.progress.emit(k, n),
                  on_done=lambda results: self._export_done(results, out_dir),
                  on_failed=self._export_failed, owner=self)

    def _on_progress(self, k: int, n: int) -> None:
        self.progress.setValue(round(100 * k / n) if n else 100)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for w in (self.queue, self.inspector, self.canvas):
            w.setEnabled(enabled)

    def _finish_export(self) -> None:
        self._exporting = False
        self._set_inputs_enabled(True)
        pending, self._pending_settings = self._pending_settings, None
        if pending is not None:
            self.set_settings(pending)
        self.model.refresh()
        self._update_state()

    def _export_done(self, results, out_dir: Path) -> None:
        self._finish_export()
        self.progress.setValue(100)
        ok = sum(1 for r in results if r.ok)
        err = len(results) - ok
        folder = next((r.output.parent for r in results if r.ok and r.output), out_dir)
        self._export_finished(ok, err, folder)

    def _export_failed(self, message: str) -> None:
        self._finish_export()
        self._info("Exportación", f"No se pudo exportar: {message}")

    # --- mejora con IA (una imagen a la vez) ----------------------------------------
    @staticmethod
    def _contains(items: list[JobItem], item: JobItem) -> bool:
        return any(x is item for x in items)

    def _maybe_enqueue(self, item: JobItem) -> None:
        row = self._row_of(item)
        if (row < 0 or item is self._enhancing or self._contains(self._enhance_queue, item)
                or self._contains(self._skip_enhance, item)):
            return
        if self.controller.needs_enhancement(row) > 0:
            self._enhance_queue.append(item)
            self._pump_enhance()

    def _pump_enhance(self) -> None:
        if self._enhancing is not None:
            return
        while self._enhance_queue:
            item = self._enhance_queue.pop(0)
            row = self._row_of(item)
            if row >= 0 and self.controller.needs_enhancement(row) > 0:
                break
        else:
            self._update_state()
            return
        self._enhancing = item
        self._cancel_enhance = threading.Event()
        item.enhancing = True
        self.model.refresh(row)
        if row == self._current_index():
            self._show_diagnosis(row)
        self._update_state()
        run_async(self._run_enhance, item, self._cancel_enhance,
                  on_done=lambda res, it=item: self._enhance_done(it, res),
                  on_failed=lambda msg, it=item: self._enhance_failed(it, msg), owner=self)

    def _run_enhance(self, item: JobItem, cancel: threading.Event) -> EnhanceResult | None:
        row = self._row_of(item)
        if row < 0:
            return None
        try:
            return self.controller.enhance(row, self.enhancer, cancel=cancel)
        except EnhanceCancelled:
            item.error = None
            return None
        finally:
            item.enhancing = False

    def _enhance_finished(self, item: JobItem) -> None:
        item.enhancing = False
        self._enhancing = None
        row = self._row_of(item)
        if row >= 0:
            self.model.refresh(row)
            if row == self._current_index():
                self._show_diagnosis(row)
                self._redraw_current()
        self._pump_enhance()
        self._update_state()

    def _enhance_done(self, item: JobItem, result) -> None:
        if result is None:  # cancelada: no volver a intentarlo sola
            self._skip_enhance.append(item)
        self._enhance_finished(item)

    def _enhance_failed(self, item: JobItem, _message: str) -> None:
        self._skip_enhance.append(item)
        self._enhance_finished(item)

    def _cancel_enhancements(self) -> None:
        self._skip_enhance.extend(self._enhance_queue)
        if self._enhancing is not None:
            self._skip_enhance.append(self._enhancing)
        self._enhance_queue.clear()
        self._cancel_enhance.set()
        self._update_state()

    def _drop_removed_enhancements(self) -> None:
        items = self.controller.items
        self._enhance_queue = [it for it in self._enhance_queue if self._contains(items, it)]
        if self._enhancing is not None and not self._contains(items, self._enhancing):
            self._cancel_enhance.set()

    def _on_enhance_choice(self, choice) -> None:
        i = self._current_index()
        if i < 0 or self._exporting:
            return
        item = self.controller.items[i]
        self.controller.set_enhance_choice(i, choice)
        self._skip_enhance = [x for x in self._skip_enhance if x is not item]
        self._maybe_enqueue(item)
        self.model.refresh(i)
        self._show_diagnosis(i)
        self._redraw_current()
        self._update_state()

    def _toggle_before_after(self) -> None:
        self._show_original = not self._show_original
        self._redraw_current()
        self._update_state()

    # --- Gemini web (gratis, semiautomático) ----------------------------------------
    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _reveal(self, path: Path) -> None:
        try:
            subprocess.Popen(reveal_command(path))  # noqa: S603
        except OSError:
            pass

    def _on_gemini(self) -> None:
        i = self._current_index()
        if i < 0:
            return
        item = self.controller.items[i]
        QGuiApplication.clipboard().setText(self.settings.gemini_prompt)
        self._open_url(GEMINI_URL)
        self._reveal(item.path)
        self._gemini_hint = ("Prompt copiado. En Gemini: sube la imagen, pega con Ctrl+V y "
                             "descarga el resultado. Luego suéltalo en «Suelta aquí la mejorada».")
        self._update_state()

    def _on_external_dropped(self, path: Path) -> None:
        i = self._current_index()
        if i < 0 or self._exporting:
            return
        item = self.controller.items[i]
        item.enhancing = True
        self.model.refresh(i)
        self._show_diagnosis(i)
        run_async(self._attach, item, Path(path),
                  on_done=lambda res, it=item: self._attach_done(it, res),
                  on_failed=lambda msg, it=item: self._attach_failed(it, msg), owner=self)

    def _attach(self, item: JobItem, path: Path):
        try:
            row = self._row_of(item)
            if row < 0:
                return None
            return self.controller.attach_external(row, path, self.enhancer)
        finally:
            item.enhancing = False

    def _attach_done(self, item: JobItem, res) -> None:
        item.enhancing = False
        self._gemini_hint = None
        self._show_original = False
        row = self._row_of(item)
        if row >= 0:
            self.model.refresh(row)
            if row == self._current_index():
                self._show_diagnosis(row)
                self._redraw_current()
        self._update_state()
        if res is not None and res.aspect_warning:
            self._info("Mejora con Gemini",
                       "La imagen mejorada tiene otra proporción (Gemini la recortó o "
                       "extendió). Se ajustará sin deformarla.")

    def _attach_failed(self, item: JobItem, message: str) -> None:
        item.enhancing = False
        row = self._row_of(item)
        if row >= 0:
            self.model.refresh(row)
            if row == self._current_index():
                self._show_diagnosis(row)
        self._update_state()
        self._info("Mejora con Gemini", f"No se pudo usar esa imagen: {message}")
