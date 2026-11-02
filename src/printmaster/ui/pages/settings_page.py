"""Página de configuración."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from printmaster.core.enhance.gemini_api import API_NOTE
from printmaster.core.enhance.gemini_web import DEFAULT_PROMPT
from printmaster.core.enhance.installer import find_engine, install_engine
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.domain.units import Unit
from printmaster.infra import paths
from printmaster.infra.settings import Settings, save_settings
from printmaster.ui.workers import run_async


class SettingsPage(QWidget):
    settings_changed = Signal(object)  # Settings
    engine_changed = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings.model_copy(deep=True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 30, 30, 30)
        title = QLabel("Configuración")
        title.setObjectName("title")
        lay.addWidget(title)

        out_box = QGroupBox("Salida")
        form = QFormLayout(out_box)
        row = QHBoxLayout()
        self.output_edit = QLineEdit(str(self.settings.output_dir))
        self.output_edit.setReadOnly(True)
        self.change_output_btn = QPushButton("Cambiar…")
        self.change_output_btn.clicked.connect(self._choose_output)
        row.addWidget(self.output_edit, 1)
        row.addWidget(self.change_output_btn)
        form.addRow("Carpeta de PDF:", row)
        self.prefix_edit = QLineEdit(self.settings.naming_prefix)
        form.addRow("Prefijo del nombre:", self.prefix_edit)
        self.digits_spin = QSpinBox()
        self.digits_spin.setRange(1, 8)
        self.digits_spin.setValue(self.settings.naming_digits)
        form.addRow("Dígitos de numeración:", self.digits_spin)
        self.by_date_check = QCheckBox("Organizar por fecha (una carpeta por día)")
        self.by_date_check.setChecked(self.settings.naming_by_date)
        form.addRow("", self.by_date_check)
        lay.addWidget(out_box)

        defaults_box = QGroupBox("Valores por defecto")
        form2 = QFormLayout(defaults_box)
        self.ppi_spin = QSpinBox()
        self.ppi_spin.setRange(50, 600)
        self.ppi_spin.setSuffix(" PPI")
        self.ppi_spin.setValue(self.settings.default_ppi)
        form2.addRow("Resolución de salida:", self.ppi_spin)
        self.unit_combo = QComboBox()
        for unit, label in ((Unit.CM, "Centímetros"), (Unit.MM, "Milímetros"),
                            (Unit.IN, "Pulgadas")):
            self.unit_combo.addItem(label, unit)
        self.unit_combo.setCurrentIndex(self.unit_combo.findData(self.settings.default_unit))
        form2.addRow("Unidad:", self.unit_combo)
        lay.addWidget(defaults_box)

        price_box = QGroupBox("Precios y lámina")
        form3 = QFormLayout(price_box)
        self.roll_width_spin = QSpinBox()
        self.roll_width_spin.setRange(21, 61)
        self.roll_width_spin.setSuffix(" cm")
        self.roll_width_spin.setValue(round(self.settings.roll_width_mm / 10))
        form3.addRow("Ancho del rollo:", self.roll_width_spin)
        self.price_short_spin = self._money(self.settings.price_short)
        form3.addRow(f"Precio 60 × {self.settings.ref_short_mm // 10} cm:", self.price_short_spin)
        self.price_long_spin = self._money(self.settings.price_long)
        form3.addRow(f"Precio 60 × {self.settings.ref_long_mm // 10} cm:", self.price_long_spin)
        self.min_price_spin = self._money(self.settings.min_price)
        form3.addRow("Precio mínimo:", self.min_price_spin)
        lay.addWidget(price_box)

        ai_box = QGroupBox("Mejora con IA")
        form4 = QFormLayout(ai_box)
        self.enhance_check = QCheckBox("Mejorar automáticamente imágenes de baja calidad")
        self.enhance_check.setChecked(self.settings.enhance_enabled)
        form4.addRow("", self.enhance_check)
        self.target_ppi_spin = QSpinBox()
        self.target_ppi_spin.setRange(72, 300)
        self.target_ppi_spin.setSuffix(" PPI")
        self.target_ppi_spin.setValue(self.settings.enhance_target_ppi)
        form4.addRow("Resolución objetivo:", self.target_ppi_spin)
        self.engine_status_label = QLabel("")
        self.engine_status_label.setWordWrap(True)
        form4.addRow("Motor Real-ESRGAN:", self.engine_status_label)
        engine_row = QHBoxLayout()
        self.install_engine_btn = QPushButton("Instalar motor de mejora")
        self.test_engine_btn = QPushButton("Probar motor")
        engine_row.addWidget(self.install_engine_btn)
        engine_row.addWidget(self.test_engine_btn)
        engine_row.addStretch(1)
        form4.addRow("", engine_row)
        self.install_engine_btn.clicked.connect(self._install_engine)
        self.test_engine_btn.clicked.connect(self._test_engine)
        lay.addWidget(ai_box)
        self._refresh_engine_status()

        gem_box = QGroupBox("Gemini (web, gratis)")
        gem = QVBoxLayout(gem_box)
        gem.addWidget(QLabel("Prompt que se copia al pulsar «Mejorar en Gemini»:"))
        self.gemini_prompt_edit = QPlainTextEdit(self.settings.gemini_prompt)
        self.gemini_prompt_edit.setFixedHeight(80)
        gem.addWidget(self.gemini_prompt_edit)
        reset_row = QHBoxLayout()
        self.reset_prompt_btn = QPushButton("Restaurar prompt original")
        self.reset_prompt_btn.clicked.connect(
            lambda: self.gemini_prompt_edit.setPlainText(DEFAULT_PROMPT))
        reset_row.addWidget(self.reset_prompt_btn)
        reset_row.addStretch(1)
        gem.addLayout(reset_row)
        api = QLabel(API_NOTE)
        api.setObjectName("hint")
        api.setWordWrap(True)
        gem.addWidget(api)
        lay.addWidget(gem_box)

        fav_box = QGroupBox("Formatos favoritos")
        fav_lay = QVBoxLayout(fav_box)
        self.favorites_list = QListWidget()
        fav_lay.addWidget(self.favorites_list)
        self.delete_favorite_btn = QPushButton("Eliminar favorito")
        self.delete_favorite_btn.clicked.connect(self._delete_favorite)
        fav_lay.addWidget(self.delete_favorite_btn, 0, Qt.AlignLeft)
        lay.addWidget(fav_box, 1)

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self.save)
        self.status_label = QLabel("")
        bottom = QHBoxLayout()
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.save_btn)
        lay.addLayout(bottom)
        self._fill_favorites()

    @staticmethod
    def _money(value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 10_000_000)
        spin.setSingleStep(500)
        spin.setPrefix("$ ")
        spin.setGroupSeparatorShown(True)
        spin.setValue(value)
        return spin

    # --- motor de mejora ------------------------------------------------------------
    def _refresh_engine_status(self, message: str | None = None) -> None:
        if message is not None:
            self.engine_status_label.setText(message)
        elif find_engine() is None:
            self.engine_status_label.setText("No instalado. Sin él se usa la mejora básica.")
        else:
            self.engine_status_label.setText("Instalado (pulse «Probar motor» para verificarlo).")

    def _set_engine_busy(self, busy: bool, text: str = "") -> None:
        self.install_engine_btn.setEnabled(not busy)
        self.test_engine_btn.setEnabled(not busy)
        if text:
            self.engine_status_label.setText(text)

    @staticmethod
    def _install_and_test() -> tuple[bool, str]:
        exe = install_engine()
        return RealEsrgan([str(exe)]).self_test(paths.data_dir() / "cache" / "selftest")

    @staticmethod
    def _run_self_test() -> tuple[bool, str]:
        engine = find_engine()
        if engine is None:
            return False, "No instalado. Sin él se usa la mejora básica."
        return engine.self_test(paths.data_dir() / "cache" / "selftest")

    def _install_engine(self) -> None:
        self._set_engine_busy(True, "Descargando e instalando el motor (≈45 MB)…")
        run_async(self._install_and_test, on_done=self._engine_result,
                  on_failed=self._engine_failed, owner=self)

    def _test_engine(self) -> None:
        self._set_engine_busy(True, "Probando el motor…")
        run_async(self._run_self_test, on_done=self._engine_result,
                  on_failed=self._engine_failed, owner=self)

    def _engine_result(self, result: tuple[bool, str]) -> None:
        ok, message = result
        self._set_engine_busy(False)
        self._refresh_engine_status(("✓ " if ok else "✕ ") + message)
        self.engine_changed.emit()

    def _engine_failed(self, message: str) -> None:
        self._set_engine_busy(False)
        self._refresh_engine_status(f"✕ {message}")
        self.engine_changed.emit()

    def _fill_favorites(self) -> None:
        self.favorites_list.clear()
        for fav in self.settings.favorites:
            self.favorites_list.addItem(QListWidgetItem(fav.name))

    def set_settings(self, settings: Settings) -> None:
        """Refresca la página cuando otra parte de la app guarda (p. ej. un favorito nuevo)."""
        self.settings = settings.model_copy(deep=True)
        self._fill_favorites()

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de salida",
                                                  str(self.settings.output_dir))
        if folder:
            self.output_edit.setText(folder)

    def _delete_favorite(self) -> None:
        row = self.favorites_list.currentRow()
        if row >= 0:
            del self.settings.favorites[row]
            self._fill_favorites()

    def save(self) -> None:
        s = self.settings
        s.output_dir = Path(self.output_edit.text())
        s.naming_prefix = self.prefix_edit.text().strip() or "Cliente"
        s.naming_digits = self.digits_spin.value()
        s.naming_by_date = self.by_date_check.isChecked()
        s.default_ppi = self.ppi_spin.value()
        s.default_unit = Unit(self.unit_combo.currentData())
        s.roll_width_mm = self.roll_width_spin.value() * 10
        s.price_short = self.price_short_spin.value()
        s.price_long = self.price_long_spin.value()
        s.min_price = self.min_price_spin.value()
        s.enhance_enabled = self.enhance_check.isChecked()
        s.enhance_target_ppi = self.target_ppi_spin.value()
        s.gemini_prompt = self.gemini_prompt_edit.toPlainText().strip() or DEFAULT_PROMPT
        save_settings(s)
        self.status_label.setText("Configuración guardada.")
        self.settings_changed.emit(s.model_copy(deep=True))
