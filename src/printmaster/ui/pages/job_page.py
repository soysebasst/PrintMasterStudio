"""Página "Nuevo trabajo": cola, vista previa, inspector, aprobación y exportación."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage
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
from printmaster.core.image_loader import load_proxy
from printmaster.core.pdf_writer import ExportOptions
from printmaster.domain.models import FitMode, ItemStatus
from printmaster.infra.settings import FavoriteFormat, Settings
from printmaster.printers.profiles import PrinterProfile
from printmaster.ui.models.queue_model import QueueModel
from printmaster.ui.qt_images import pil_to_qimage
from printmaster.ui.widgets.diagnosis_card import DiagnosisCard
from printmaster.ui.widgets.inspector import Inspector
from printmaster.ui.widgets.preview_canvas import PreviewCanvas
from printmaster.ui.widgets.queue_view import QueueView
from printmaster.ui.workers import run_async

PREVIEW_SIDE = 1600
PREVIEW_CACHE = 8
STEPS = ["① Cargar", "② Formato", "③ Revisar", "④ Exportar"]


class _ProgressBridge(QObject):
    progress = Signal(int, int)


class JobPage(QWidget):
    def __init__(self, settings: Settings, profile: PrinterProfile, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.profile = profile
        self.controller = JobController(settings, profile)
        self.model = QueueModel(self.controller)
        self._previews: OrderedDict[Path, QImage] = OrderedDict()
        self._exporting = False
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
        for b in (self.zoom_out_btn, self.fit_btn, self.zoom_in_btn):
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
        self.diagnosis = DiagnosisCard()
        side_lay.addWidget(self.inspector)
        side_lay.addWidget(self.diagnosis)
        side_lay.addStretch(1)
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
        self.queue.current_changed.connect(self._on_current_changed)
        self.queue.paths_added.connect(self._on_paths_added)
        self.model.rowsRemoved.connect(lambda *a: self._after_queue_change())
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
    def apply_favorite(self, fav: FavoriteFormat) -> None:
        self.inspector.apply_favorite(fav)

    def set_settings(self, settings: Settings) -> None:
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
        issues = self.controller.issues()
        self.inspector.show_issues(issues)
        has_errors = any(i.level == "error" for i in issues)
        approved = any(it.status == ItemStatus.APPROVED for it in items)
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
        self.export_btn.setEnabled(approved and not has_errors and not busy)
        self.approve_all_btn.setEnabled(bool(items) and not busy)
        cur = self._current_index()
        self.approve_btn.setEnabled(
            cur >= 0 and items[cur].status in (ItemStatus.READY, ItemStatus.EXPORTED)
            and not busy)

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
                      on_failed=lambda _msg: None, owner=self)

    def _row_of(self, item: JobItem) -> int:
        for i, it in enumerate(self.controller.items):
            if it is item:
                return i
        return -1

    def _analysis_done(self, item: JobItem) -> None:
        row = self._row_of(item)
        if row < 0:
            return
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
        self._apply_params()
        self.model.refresh()
        self._redraw_current()
        self._schedule_analysis(list(self.controller.items))
        self._update_state()

    def _on_crop_changed(self, crop) -> None:
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
        self.diagnosis.show_diagnosis(item.diagnosis, item.info, downsample, item.error)

    def _redraw_current(self) -> None:
        row = self._current_index()
        if row < 0:
            return
        item = self.controller.items[row]
        if item.info is None:
            self.canvas.clear()
            return
        cached = self._previews.get(item.path)
        if cached is not None:
            self._draw(item, cached)
            return
        run_async(load_proxy, item.path, PREVIEW_SIDE,
                  on_done=lambda img, it=item: self._preview_loaded(it, img),
                  on_failed=lambda _m: None, owner=self)

    def _preview_loaded(self, item: JobItem, img) -> None:
        qimg = pil_to_qimage(img)
        self._previews[item.path] = qimg
        while len(self._previews) > PREVIEW_CACHE:
            self._previews.popitem(last=False)
        row = self._row_of(item)
        if row >= 0 and row == self._current_index():
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
        self.canvas.show_plan(qimg, plan, FitMode(self.controller.mode), self.profile,
                              (item.info.width_px, item.info.height_px))
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
        if skipped:
            self._info("Aprobación", f"Se omitieron {len(skipped)} imágenes con baja "
                       "resolución. Revíselas y apruébelas una por una.")

    def _export(self) -> None:
        if self._exporting:
            return
        self._exporting = True
        self.progress.setValue(0)
        self.queue.setEnabled(False)
        self.inspector.setEnabled(False)
        self._update_state()
        out_dir = Path(self.settings.output_dir)
        run_async(self.controller.export, None, out_dir,
                  lambda k, n: self._bridge.progress.emit(k, n),
                  on_done=lambda results: self._export_done(results, out_dir),
                  on_failed=self._export_failed, owner=self)

    def _on_progress(self, k: int, n: int) -> None:
        self.progress.setValue(round(100 * k / n) if n else 100)

    def _finish_export(self) -> None:
        self._exporting = False
        self.queue.setEnabled(True)
        self.inspector.setEnabled(True)
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
