"""Página "Nuevo trabajo": cola, vista previa, inspector, aprobación y exportación."""

from __future__ import annotations

import hashlib
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from printmaster.app_services.job_controller import JobController, JobItem
from printmaster.app_services.next_step import next_step
from printmaster.core.enhance.download_watch import DownloadWatch
from printmaster.core.enhance.enhancer import ENGINE_AI, Enhancer, EnhanceResult
from printmaster.core.enhance.gemini_web import reveal_command
from printmaster.core.enhance.installer import find_engine
from printmaster.core.enhance.realesrgan import EnhanceCancelled
from printmaster.core.image_loader import SUPPORTED_EXTENSIONS, load_proxy
from printmaster.core.pdf_writer import ExportOptions
from printmaster.core.pricing import format_cop, suggest_price
from printmaster.domain.models import CropRect, FitMode, ItemStatus
from printmaster.infra import paths
from printmaster.infra.settings import FavoriteFormat, Settings
from printmaster.printers.profiles import PrinterProfile
from printmaster.ui.icons import icon
from printmaster.ui.models.queue_model import QueueModel
from printmaster.ui.qt_images import pil_to_qimage
from printmaster.ui.widgets.crop_dialog import CropDialog
from printmaster.ui.widgets.inspector import Inspector
from printmaster.ui.widgets.preview_canvas import PreviewCanvas
from printmaster.ui.widgets.quality_panel import QualityPanel
from printmaster.ui.widgets.queue_view import QueueView
from printmaster.ui.workers import run_async

PREVIEW_SIDE = 1600
CLIPBOARD_SIDE = 3072  # lado mayor máximo de la imagen que se copia para Gemini
WAIT_TIMEOUT_S = 900  # 15 minutos esperando la descarga de Gemini
WATCH_INTERVAL_MS = 1000
MSG_COPIED = ("Imagen copiada. En Gemini: Ctrl+V y enviar. Luego descargue el resultado o "
              "cópielo (clic derecho › Copiar imagen) y pulse Ctrl+V aquí.")
MSG_EXPIRED = "Ya no se espera la descarga de Gemini."
MSG_SAME_IMAGE = ("El portapapeles todavía tiene la imagen original. En Gemini use clic "
                  "derecho › Copiar imagen sobre el resultado.")
MSG_NO_IMAGE = "No hay ninguna imagen en el portapapeles."
MAX_BACKGROUND_THREADS = 2  # especificación R5: como máximo 2 imágenes decodificándose a la vez
PREVIEW_CACHE = 8
STEPS = ["1  Cargar", "2  Revisar", "3  Exportar"]


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
        self._attaching: JobItem | None = None  # el último adjunto en curso
        self._attach_cancels: dict[int, threading.Event] = {}  # id(item) -> cancelación
        self._waits: list[tuple[JobItem, float]] = []  # en espera de Gemini (FIFO), con su inicio
        self._watch: DownloadWatch | None = None
        self._consumed: set[Path] = set()
        self._copied_digest: tuple[int, int, str] | None = None
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._poll_downloads)
        self._exporting = False
        self._pending_settings: Settings | None = None
        self._bridge = _ProgressBridge()
        self._bridge.progress.connect(self._on_progress)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget()
        header.setObjectName("pageHeader")
        head = QHBoxLayout(header)
        head.setContentsMargins(16, 10, 16, 10)
        title = QLabel("Nuevo trabajo")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addSpacing(16)
        self.step_chips: list[QLabel] = []
        for text in STEPS:
            chip = QLabel(text)
            chip.setObjectName("stepChip")
            self.step_chips.append(chip)
            head.addWidget(chip)
        head.addStretch(1)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        self.queue = QueueView(self.model)
        self.queue.setMinimumWidth(190)
        splitter.addWidget(self.queue)

        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        self.canvas = PreviewCanvas()
        center_lay.addWidget(self.canvas, 1)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(8, 8, 8, 4)
        self.original_btn = QPushButton("Original")
        self.enhanced_btn = QPushButton("Mejorada")
        self._compare_group = QButtonGroup(self)
        for b in (self.original_btn, self.enhanced_btn):
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setEnabled(False)
            self._compare_group.addButton(b)
            top_row.addWidget(b)
        self.enhanced_btn.setChecked(True)
        self.original_btn.setToolTip("Ver la imagen original")
        self.enhanced_btn.setToolTip("Ver la versión mejorada")
        top_row.addSpacing(8)
        self.crop_btn = QPushButton("  Recortar")
        self.crop_btn.setIcon(icon("crop", size=18))
        self.crop_btn.setToolTip("Elegir a mano qué parte de la imagen se imprime")
        self.crop_btn.setEnabled(False)
        top_row.addWidget(self.crop_btn)
        top_row.addStretch(1)
        self.zoom_out_btn = QPushButton()
        self.fit_btn = QPushButton()
        self.zoom_in_btn = QPushButton()
        for b, tip, name in ((self.zoom_out_btn, "Alejar", "zoom-out"),
                             (self.fit_btn, "Ajustar a la vista", "maximize"),
                             (self.zoom_in_btn, "Acercar", "zoom-in")):
            b.setObjectName("iconButton")
            b.setToolTip(tip)
            b.setIcon(icon(name, size=18))
            top_row.addWidget(b)
        center_lay.insertLayout(0, top_row)
        self.info_label = QLabel("")
        self.info_label.setObjectName("muted")
        self.info_label.setAlignment(Qt.AlignCenter)
        center_lay.addWidget(self.info_label)
        self.ppi_info = self.info_label
        splitter.addWidget(center)

        side = QWidget()
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        self.inspector = Inspector(settings)
        self.quality = QualityPanel()
        self.diagnosis = self.quality  # compatibilidad: show_diagnosis() / text()
        self.inspector.layout().insertWidget(self.inspector.quality_insert_index(), self.quality)
        self.quality.choice_row.addWidget(self.inspector.enhance_combo, 1)
        self.quality.choice_row.setSpacing(6)
        self.inspector.toggles_row.insertWidget(0, self.quality.details_toggle)
        side_lay.addWidget(self.inspector)
        self.side_panel = side
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(side)
        scroll.setMinimumWidth(310)
        scroll.setMaximumWidth(380)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 760, 330])
        root.addWidget(splitter, 1)

        footer = QWidget()
        footer.setObjectName("pageFooter")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(16, 10, 16, 10)
        self.next_label = QLabel("")
        self.next_label.setObjectName("nextLabel")
        self.next_label.setWordWrap(True)
        bottom.addWidget(self.next_label, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        bottom.addWidget(self.progress)
        self.total_label = QLabel("")
        self.total_label.setObjectName("total_label")
        bottom.addWidget(self.total_label)
        self.cancel_enhance_btn = QPushButton("Cancelar mejora")
        self.cancel_enhance_btn.setVisible(False)
        bottom.addWidget(self.cancel_enhance_btn)
        self.approve_btn = QPushButton("Aprobar esta")
        self.approve_btn.setToolTip("Aprobar la imagen seleccionada")
        self.quality.choice_row.addWidget(self.approve_btn, 1)
        self.approve_all_btn = QPushButton("Aprobar todo")
        self.export_btn = QPushButton("Exportar PDF")
        self.export_btn.setProperty("primary", True)
        self.export_btn.setIcon(icon("download", "#ffffff", 18))
        for b in (self.approve_all_btn, self.export_btn):
            bottom.addWidget(b)
        root.addWidget(footer)

        # conexiones
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        self.fit_btn.clicked.connect(self.canvas.fit)
        self.original_btn.clicked.connect(lambda: self._set_compare(True))
        self.enhanced_btn.clicked.connect(lambda: self._set_compare(False))
        self.cancel_enhance_btn.clicked.connect(self._cancel_enhancements)
        self.inspector.enhance_choice_changed.connect(self._on_enhance_choice)
        self.quality.gemini_btn.clicked.connect(self._on_gemini)
        self.quality.drop_zone.file_dropped.connect(self._on_external_dropped)
        self.quality.paste_btn.clicked.connect(self._paste_from_clipboard)
        self.quality.stop_wait_btn.clicked.connect(self._stop_waiting)
        self.quality.copy_prompt_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.settings.gemini_prompt))
        self._paste_shortcut = QShortcut(QKeySequence.Paste, self,
                                         context=Qt.WidgetWithChildrenShortcut)
        self._paste_shortcut.activated.connect(self._paste_from_clipboard)
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
        self.crop_btn.clicked.connect(self._open_crop)

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
        self.inspector._settings = settings
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
        # pasos: 0 cargar, 1 revisar, 2 exportar
        current = 0 if not items else (2 if step == 3 else 1)
        if items and all(it.status == ItemStatus.EXPORTED for it in items
                         if it.status != ItemStatus.ERROR):
            current = 3
        for k, chip in enumerate(self.step_chips):
            state = "done" if k < current else ("current" if k == current else "todo")
            chip.setText(("✓ " + STEPS[k].split("  ", 1)[1]) if state == "done" else STEPS[k])
            if chip.property("state") != state:
                chip.setProperty("state", state)
                chip.style().unpolish(chip)
                chip.style().polish(chip)
        busy = self._exporting
        enhancing = self._enhancing is not None or bool(self._enhance_queue) or any(
            it.enhancing for it in items)
        analyzing = any(it.info is not None and it.diagnosis is None
                        and it.status == ItemStatus.PENDING for it in items)
        hint = self._gemini_hint or next_step(self.controller, analyzing, enhancing)
        self.next_label.setText(f"Siguiente: {hint}" if not self._gemini_hint else hint)
        n_export = len(self.controller.exportable_indices()) if items else 0
        self.export_btn.setText(f"Exportar {n_export} PDF" if n_export else "Exportar PDF")
        self.export_btn.setEnabled(exportable and not busy and not enhancing)
        self.progress.setVisible(busy or enhancing)
        if not busy:
            self.progress.setRange(0, 0 if enhancing else 100)
        self.cancel_enhance_btn.setVisible(enhancing)
        count, total = self.controller.total_price()
        self.total_label.setText(
            f"{count} lámina{'s' if count != 1 else ''} · {format_cop(total)}" if count else "")
        self.approve_all_btn.setEnabled(bool(items) and not busy)
        cur = self._current_index()
        self.approve_btn.setEnabled(
            cur >= 0 and items[cur].status in (ItemStatus.READY, ItemStatus.EXPORTED)
            and not busy)
        self.crop_btn.setEnabled(cur >= 0 and items[cur].info is not None and not busy)
        has_enh = cur >= 0 and items[cur].uses_enhanced
        for b in (self.original_btn, self.enhanced_btn):
            b.setEnabled(has_enh)
        if not has_enh:
            self._show_original = False
        showing_original = self._show_original or not has_enh
        (self.original_btn if showing_original else self.enhanced_btn).setChecked(True)
        if cur >= 0 and items[cur].info is not None and not self.controller.has_errors(cur):
            w, h = (f"{(v / 10).normalize():f}".replace(".", ",")
                    for v in self.controller.page_size_for(cur))
            ppi = items[cur].diagnosis.effective_ppi if items[cur].diagnosis else None
            if self._show_original and items[cur].original_diagnosis is not None:
                ppi = items[cur].original_diagnosis.effective_ppi
            self.info_label.setText(f"{w} × {h} cm" + (f" · {ppi:.0f} PPI efectivos"
                                                        if ppi else "")
                                    + ("" if items[cur].region.is_full else " · Recortada"))
            self.inspector.set_price(self.controller.price_for(cur))
        else:
            self.info_label.setText("")
            self.inspector.set_price(None)

    def _after_queue_change(self) -> None:
        self._gemini_hint = None
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
        self._gemini_hint = None
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
        size = (src.width_px, src.height_px)
        if not item.region.is_full:  # la vista previa trabaja sobre la zona recortada
            rl, rt, rr, rb = item.region.box(*size)
            pl, pt_, pr, pb = item.region.box(qimg.width(), qimg.height())
            qimg = qimg.copy(pl, pt_, pr - pl, pb - pt_)
            l, t, r, b = plan.src_box
            plan = replace(plan, src_box=(l - rl, t - rt, r - rl, b - rt))
            size = (rr - rl, rb - rt)
        self.canvas.show_plan(qimg, plan, FitMode(self.controller.mode), self.profile, size)
        self._update_state()

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
        gemini = sum(1 for it in approved if it.enhanced.engine.startswith("Gemini"))
        ai = sum(1 for it in approved if it.enhanced.engine == ENGINE_AI)
        basic = len(approved) - ai - gemini
        compare = "revíselas con «Original» y «Mejorada»."
        if gemini:
            messages.append(f"Se mejoraron {gemini} imágenes con Gemini: {compare}")
        if ai:
            messages.append(f"Se mejoraron {ai} imágenes con IA (Real-ESRGAN): {compare}")
        if basic:
            messages.append(f"Se mejoraron {basic} imágenes con la mejora básica: {compare}")
        if messages:
            self._info("Aprobación", "\n\n".join(messages))

    def _export(self) -> None:
        if self._exporting:
            return
        self._exporting = True
        self.progress.setRange(0, 100)
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
        for ev in self._attach_cancels.values():
            ev.set()
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

    def _set_compare(self, original: bool) -> None:
        self._show_original = original
        self._redraw_current()
        self._update_state()

    # --- recorte manual --------------------------------------------------------------
    def _run_crop_dialog(self, dlg: CropDialog) -> CropRect | None:
        """Muestra el diálogo (sobrescribible en pruebas)."""
        return dlg.crop_rect() if dlg.exec() == QDialog.Accepted else None

    def _crop_presets(self, row: int) -> list[tuple[str, float | None]]:
        info = self.controller.items[row].info
        presets: list[tuple[str, float | None]] = [("Libre", None)]
        if info is not None:
            presets.append(("Original", info.width_px / info.height_px))
        seen: set[float] = set()
        for fav in self.settings.favorites:
            w, h = float(fav.width), float(fav.height)
            ratio = round(w / h, 4) if h else 0
            if ratio and ratio not in seen:
                seen.add(ratio)
                presets.append((fav.name, w / h))
        return presets

    def _describe_crop(self, row: int, region: CropRect) -> str:
        try:
            plan = self.controller.plan_for(row, region=region)
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        w, h = (f"{(v / 10).normalize():f}".replace(".", ",")
                for v in (plan.page_w_mm, plan.page_h_mm))
        price = suggest_price(plan.page_w_mm, plan.page_h_mm, self.settings.pricing())
        return f"{w} × {h} cm · {format_cop(price)} sugerido · {plan.effective_ppi:.0f} PPI"

    def _open_crop(self) -> None:
        row = self._current_index()
        if row < 0 or self._exporting:
            return
        item = self.controller.items[row]
        qimg = self._previews.get(self._preview_path(item))
        if qimg is None:
            return
        dlg = CropDialog(qimg, item.region, self._crop_presets(row),
                         lambda r, i=row: self._describe_crop(i, r), self)
        region = self._run_crop_dialog(dlg)
        dlg.deleteLater()
        row = self._row_of(item)
        if region is None or row < 0:
            return
        self.controller.set_region(row, region)
        self.model.refresh(row)
        self._show_diagnosis(row)
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

    @staticmethod
    def _digest(img: QImage) -> tuple[int, int, str]:
        rgb = img.convertToFormat(QImage.Format_RGBX8888)  # 4 bytes por píxel: sin relleno
        return rgb.width(), rgb.height(), hashlib.sha1(bytes(rgb.constBits())).hexdigest()

    def _on_gemini(self) -> None:
        i = self._current_index()
        if i < 0 or self._exporting:
            return
        item = self.controller.items[i]
        try:
            qimg = pil_to_qimage(load_proxy(item.path, max_side=CLIPBOARD_SIDE))
        except Exception as exc:  # noqa: BLE001
            self._info("Mejora con Gemini", f"No se pudo copiar la imagen: {exc}")
            return
        QGuiApplication.clipboard().setImage(qimg)
        self._copied_digest = self._digest(qimg)
        if self.settings.gemini_open_mode == "web":
            self._open_url(self.settings.gemini_url)
        if self._watch is None:
            self._watch = DownloadWatch(Path(self.settings.downloads_dir), time.time() - 1)
            self._consumed = set()
        self._waits = [(it, t) for it, t in self._waits if it is not item]
        self._waits.append((item, time.monotonic()))
        self._watch_timer.start()
        self._gemini_hint = MSG_COPIED
        self._refresh_waiting()
        self._update_state()

    @property
    def _waiting(self) -> tuple[JobItem, DownloadWatch] | None:
        """La imagen en espera más antigua (la próxima en recibir una descarga)."""
        if not self._waits or self._watch is None:
            return None
        return self._waits[0][0], self._watch

    def _has_gem(self) -> bool:
        return "/gem/" in self.settings.gemini_url

    def _refresh_waiting(self) -> None:
        if not self._waits:
            self.quality.set_waiting(None)
            return
        name = self._waits[0][0].path.name
        if len(self._waits) > 1:
            name += f"» y {len(self._waits) - 1} más «"
        self.quality.set_waiting(name, show_copy_prompt=not self._has_gem())
        if self._watch is not None and not self._watch.folder_ok:
            self.quality.wait_label.setText(
                "No se encuentra la carpeta de descargas (Configuración › Gemini). "
                "Copie el resultado y pulse Ctrl+V.")

    def _unwait(self, item: JobItem) -> None:
        self._waits = [(it, t) for it, t in self._waits if it is not item]
        if not self._waits:
            self._stop_waiting()
        else:
            self._refresh_waiting()

    def _stop_waiting(self) -> None:
        self._waits = []
        self._watch = None
        self._watch_timer.stop()
        self._refresh_waiting()

    def _poll_downloads(self) -> None:
        if self._exporting:
            return  # se sigue esperando: se adjunta al terminar la exportación
        now = time.monotonic()
        alive = [(it, t) for it, t in self._waits if self._row_of(it) >= 0]
        expired = [w for w in alive if now - w[1] > WAIT_TIMEOUT_S]
        self._waits = [w for w in alive if w not in expired]
        if not self._waits or self._watch is None:
            self._stop_waiting()
            if expired:
                self._gemini_hint = MSG_EXPIRED
                self._update_state()
            return
        self._refresh_waiting()
        found = self._watch.poll(exclude=self._consumed, oldest=True)
        if found is None:
            return
        self._consumed.add(found)
        item = self._waits[0][0]
        self._unwait(item)
        self._on_external_dropped(
            found, target=item, notice=f"Mejora recibida de Gemini para «{item.path.name}»")

    def _paste_target(self) -> JobItem | None:
        i = self._current_index()
        current = self.controller.items[i] if i >= 0 else None
        waiting = [it for it, _ in self._waits if self._row_of(it) >= 0]
        if current is not None and any(it is current for it in waiting):
            return current
        return waiting[0] if waiting else current

    def _paste_from_clipboard(self) -> None:
        if isinstance(QApplication.focusWidget(), (QLineEdit, QAbstractSpinBox, QPlainTextEdit)):
            return  # Ctrl+V dentro de un campo de texto es para ese campo
        target = self._paste_target()
        if target is None or self._exporting:
            return
        clip = QGuiApplication.clipboard()
        mime = clip.mimeData()
        path: Path | None = None
        if mime is not None and mime.hasImage():
            qimg = clip.image()
            if not qimg.isNull():
                if self._copied_digest is not None and self._digest(qimg) == self._copied_digest:
                    self._info("Mejora con Gemini", MSG_SAME_IMAGE)
                    return
                folder = paths.data_dir() / "cache" / "external"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"clipboard_{time.strftime('%Y%m%d_%H%M%S')}_{id(qimg) % 1000}.png"
                if not qimg.save(str(path), "PNG", 80):
                    self._info("Mejora con Gemini", "No se pudo guardar la imagen pegada.")
                    return
        if path is None and mime is not None and mime.hasUrls():
            for url in mime.urls():
                local = Path(url.toLocalFile()) if url.isLocalFile() else None
                if local is not None and local.suffix.lower() in SUPPORTED_EXTENSIONS:
                    path = local
                    break
        if path is None:
            self._info("Mejora con Gemini", MSG_NO_IMAGE)
            return
        self._on_external_dropped(path, target=target,
                                  notice=f"Mejora pegada en «{target.path.name}»")

    def _on_external_dropped(self, path: Path, target: JobItem | None = None,
                             notice: str | None = None) -> None:
        if self._exporting:
            return
        if target is None:
            i = self._current_index()
            if i < 0:
                return
            item = self.controller.items[i]
        else:
            item = target
            i = self._row_of(item)
            if i < 0:
                return
        if id(item) in self._attach_cancels:
            self._info("Mejora con Gemini",
                       f"Ya se está adjuntando una mejora a «{item.path.name}». Espere a que "
                       "termine.")
            return
        self._unwait(item)
        if self._enhancing is item:
            self._cancel_enhance.set()  # la versión de Gemini reemplaza la mejora automática
        self._enhance_queue = [it for it in self._enhance_queue if it is not item]
        self._skip_enhance.append(item)
        self._attaching = item
        cancel = threading.Event()
        self._attach_cancels[id(item)] = cancel
        item.enhancing = True
        self.model.refresh(i)
        if i == self._current_index():
            self._show_diagnosis(i)
        self._update_state()
        run_async(self._attach, item, Path(path), cancel,
                  on_done=lambda res, it=item: self._attach_done(it, res, notice),
                  on_failed=lambda msg, it=item: self._attach_failed(it, msg), owner=self)

    def _attach(self, item: JobItem, path: Path, cancel: threading.Event | None = None):
        try:
            row = self._row_of(item)
            if row < 0:
                return None
            return self.controller.attach_external(row, path, self.enhancer,
                                                   cancel=cancel)
        finally:
            item.enhancing = False

    def _attach_finished(self, item: JobItem) -> None:
        item.enhancing = False
        self._attach_cancels.pop(id(item), None)
        if self._attaching is item:
            self._attaching = None

    def _attach_done(self, item: JobItem, res, notice: str | None = None) -> None:
        self._attach_finished(item)
        self._gemini_hint = notice if res is not None else None
        self._show_original = False
        row = self._row_of(item)
        if row >= 0:
            self.model.refresh(row)
            if row == self._current_index():
                self.inspector.set_enhance_choice(item.enhance_choice)
                self._show_diagnosis(row)
                self._redraw_current()
        self._update_state()
        if res is not None and res.aspect_warning:
            self._info("Mejora con Gemini",
                       "La imagen mejorada tiene otra proporción (Gemini la recortó o "
                       "extendió). Se ajustará sin deformarla.")

    def _attach_failed(self, item: JobItem, message: str) -> None:
        self._attach_finished(item)
        row = self._row_of(item)
        if row >= 0:
            self.model.refresh(row)
            if row == self._current_index():
                self._show_diagnosis(row)
        self._update_state()
        self._info("Mejora con Gemini", f"No se pudo usar esa imagen: {message}")
