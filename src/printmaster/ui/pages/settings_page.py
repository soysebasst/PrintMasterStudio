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
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from printmaster.domain.units import Unit
from printmaster.infra.settings import Settings, save_settings


class SettingsPage(QWidget):
    settings_changed = Signal(object)  # Settings

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
        save_settings(s)
        self.status_label.setText("Configuración guardada.")
        self.settings_changed.emit(s.model_copy(deep=True))
