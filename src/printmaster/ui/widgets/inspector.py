"""Inspector de formato: tamaño físico, unidades, orientación, PPI, modo de ajuste y fondo."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QInputDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from printmaster.domain.models import Background, BackgroundKind, FitMode, Orientation, PrintSpec
from printmaster.domain.units import Unit, from_mm, to_mm
from printmaster.infra.settings import FavoriteFormat, Settings
from printmaster.printers.profiles import ValidationIssue

PPI_PRESETS = [100, 150, 200, 250, 300]
CUSTOM_PPI = -1
DEBOUNCE_MS = 150

MODE_LABELS = [
    (FitMode.FIT_LENGTH, "Ajustar largo a la imagen"),
    (FitMode.CONTAIN, "Ajustar sin recortar"),
    (FitMode.FILL, "Rellenar"),
    (FitMode.COVER, "Recortar"),
]
BACKGROUND_LABELS = [
    (BackgroundKind.WHITE, "Blanco"),
    (BackgroundKind.COLOR, "Color…"),
    (BackgroundKind.EDGE_COLOR, "Color del borde"),
    (BackgroundKind.BLUR, "Fondo difuminado"),
]


class Inspector(QWidget):
    changed = Signal()
    favorite_saved = Signal(object)  # FavoriteFormat

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._w_mm = Decimal(600)
        self._h_mm = Decimal(900)
        self._unit = Unit(settings.default_unit)
        self._color: tuple[int, int, int] = (255, 255, 255)
        self._favorites: list[FavoriteFormat] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.changed.emit)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        fmt_box = QGroupBox("FORMATO")
        form = QFormLayout(fmt_box)
        self.favorites_combo = QComboBox()
        self.favorites_combo.setObjectName("favorites_combo")
        form.addRow("Favoritos:", self.favorites_combo)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setObjectName("width_spin")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setObjectName("height_spin")
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(0.1, 10000)
            spin.setDecimals(2)
            spin.setKeyboardTracking(False)
        form.addRow("Ancho:", self.width_spin)
        form.addRow("Largo:", self.height_spin)
        self.unit_combo = QComboBox()
        self.unit_combo.setObjectName("unit_combo")
        for unit, label in ((Unit.CM, "cm"), (Unit.MM, "mm"), (Unit.IN, "pulgadas")):
            self.unit_combo.addItem(label, unit)
        form.addRow("Unidad:", self.unit_combo)
        self.orientation_combo = QComboBox()
        self.orientation_combo.setObjectName("orientation_combo")
        for o, label in ((Orientation.AS_ENTERED, "Como se escribió"),
                         (Orientation.AUTO, "Automática"), (Orientation.PORTRAIT, "Vertical"),
                         (Orientation.LANDSCAPE, "Horizontal")):
            self.orientation_combo.addItem(label, o)
        form.addRow("Orientación:", self.orientation_combo)
        self.save_favorite_btn = QPushButton("★ Guardar formato")
        self.save_favorite_btn.setObjectName("save_favorite_btn")
        form.addRow("", self.save_favorite_btn)
        lay.addWidget(fmt_box)

        out_box = QGroupBox("SALIDA")
        form2 = QFormLayout(out_box)
        self.ppi_combo = QComboBox()
        self.ppi_combo.setObjectName("ppi_combo")
        for ppi in PPI_PRESETS:
            self.ppi_combo.addItem(f"{ppi} PPI", ppi)
        self.ppi_combo.addItem("Personalizado…", CUSTOM_PPI)
        form2.addRow("Resolución:", self.ppi_combo)
        self.ppi_spin = QSpinBox()
        self.ppi_spin.setObjectName("ppi_spin")
        self.ppi_spin.setRange(50, 600)
        self.ppi_spin.setSuffix(" PPI")
        self.ppi_spin.setKeyboardTracking(False)
        form2.addRow("", self.ppi_spin)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("mode_combo")
        for mode, label in MODE_LABELS:
            self.mode_combo.addItem(label, mode)
        form2.addRow("Ajuste:", self.mode_combo)
        self.background_label = QLabel("Fondo:")
        self.background_combo = QComboBox()
        self.background_combo.setObjectName("background_combo")
        for kind, label in BACKGROUND_LABELS:
            self.background_combo.addItem(label, kind)
        form2.addRow(self.background_label, self.background_combo)
        self.lossless_check = QCheckBox("Exportar sin pérdida")
        self.lossless_check.setObjectName("lossless_check")
        self.lossless_check.setChecked(True)
        self.lossless_check.setToolTip(
            "Desactivado: las fotos JPEG que deban reducirse se guardan como JPEG de calidad 95.")
        form2.addRow("", self.lossless_check)
        lay.addWidget(out_box)

        self.issues_label = QLabel("")
        self.issues_label.setObjectName("issues_label")
        self.issues_label.setWordWrap(True)
        self.issues_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.issues_label)
        lay.addStretch(1)

        # valores iniciales
        self.unit_combo.setCurrentIndex(self.unit_combo.findData(self._unit))
        self.ppi_spin.setValue(settings.default_ppi)
        preset = self.ppi_combo.findData(settings.default_ppi)
        self.ppi_combo.setCurrentIndex(preset if preset >= 0 else
                                       self.ppi_combo.findData(CUSTOM_PPI))
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(settings.default_mode))
        self.orientation_combo.setCurrentIndex(
            self.orientation_combo.findData(settings.default_orientation))
        self.set_favorites(settings.favorites)
        self._refresh_spins()
        self._update_visibility()

        # señales
        self.width_spin.valueChanged.connect(self._on_width)
        self.height_spin.valueChanged.connect(self._on_height)
        self.unit_combo.currentIndexChanged.connect(self._on_unit)
        self.orientation_combo.currentIndexChanged.connect(self._emit)
        self.ppi_combo.currentIndexChanged.connect(self._on_ppi_combo)
        self.ppi_spin.valueChanged.connect(self._emit)
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        self.background_combo.currentIndexChanged.connect(self._emit)
        self.background_combo.activated.connect(self._on_background_activated)
        self.lossless_check.toggled.connect(self._emit)
        self.favorites_combo.currentIndexChanged.connect(self._on_favorite)
        self.save_favorite_btn.clicked.connect(self._save_favorite)

    # --- API ------------------------------------------------------------------------
    def spec(self) -> PrintSpec:
        return PrintSpec(self._w_mm, self._h_mm, self.ppi(),
                         Orientation(self.orientation_combo.currentData()))

    def ppi(self) -> int:
        data = self.ppi_combo.currentData()
        return self.ppi_spin.value() if data == CUSTOM_PPI else int(data)

    def mode(self) -> FitMode:
        return FitMode(self.mode_combo.currentData())

    def background(self) -> Background:
        kind = BackgroundKind(self.background_combo.currentData())
        if kind == BackgroundKind.COLOR:
            return Background(kind, self._color)
        return Background(kind)

    def lossless(self) -> bool:
        return self.lossless_check.isChecked()

    def unit(self) -> Unit:
        return self._unit

    def set_spec_values(self, width_mm: Decimal, height_mm: Decimal, unit: Unit) -> None:
        self._w_mm, self._h_mm = Decimal(width_mm), Decimal(height_mm)
        self._unit = Unit(unit)
        self.unit_combo.blockSignals(True)
        self.unit_combo.setCurrentIndex(self.unit_combo.findData(self._unit))
        self.unit_combo.blockSignals(False)
        self._refresh_spins()
        self._emit()

    def set_spec(self, spec: PrintSpec, unit: Unit) -> None:
        self.orientation_combo.setCurrentIndex(self.orientation_combo.findData(spec.orientation))
        preset = self.ppi_combo.findData(spec.ppi)
        if preset >= 0:
            self.ppi_combo.setCurrentIndex(preset)
        else:
            self.ppi_combo.setCurrentIndex(self.ppi_combo.findData(CUSTOM_PPI))
            self.ppi_spin.setValue(spec.ppi)
        self.set_spec_values(spec.width_mm, spec.height_mm, unit)

    def set_favorites(self, favorites: list[FavoriteFormat]) -> None:
        self._favorites = list(favorites)
        self.favorites_combo.blockSignals(True)
        self.favorites_combo.clear()
        self.favorites_combo.addItem("Elegir…", None)
        for i, fav in enumerate(self._favorites):
            self.favorites_combo.addItem(fav.name, i)
        self.favorites_combo.blockSignals(False)

    def apply_favorite(self, fav: FavoriteFormat) -> None:
        self.set_spec_values(to_mm(fav.width, fav.unit), to_mm(fav.height, fav.unit), fav.unit)

    def show_issues(self, issues: list[ValidationIssue]) -> None:
        parts = []
        for issue in issues:
            color = "#ff6b6b" if issue.level == "error" else "#f0b429"
            icon = "✕" if issue.level == "error" else "▲"
            parts.append(f'<span style="color:{color}">{icon} {issue.message}</span>')
        self.issues_label.setText("<br>".join(parts))

    # --- internos -------------------------------------------------------------------
    def _emit(self, *args) -> None:
        self._timer.start()

    def _display(self, mm: Decimal) -> float:
        return float(round(from_mm(mm, self._unit), 2))

    def _refresh_spins(self) -> None:
        for spin, mm in ((self.width_spin, self._w_mm), (self.height_spin, self._h_mm)):
            spin.blockSignals(True)
            spin.setValue(self._display(mm))
            spin.blockSignals(False)

    def _on_width(self, value: float) -> None:
        self._w_mm = to_mm(Decimal(str(round(value, 2))), self._unit)
        self._emit()

    def _on_height(self, value: float) -> None:
        self._h_mm = to_mm(Decimal(str(round(value, 2))), self._unit)
        self._emit()

    def _on_unit(self, _index: int) -> None:
        self._unit = Unit(self.unit_combo.currentData())
        self._refresh_spins()

    def _on_ppi_combo(self, _index: int) -> None:
        self._update_visibility()
        self._emit()

    def _on_mode(self, _index: int) -> None:
        self._update_visibility()
        self._emit()

    def _update_visibility(self) -> None:
        self.ppi_spin.setVisible(self.ppi_combo.currentData() == CUSTOM_PPI)
        fill = self.mode_combo.currentData() == FitMode.FILL
        self.background_combo.setVisible(fill)
        self.background_label.setVisible(fill)

    def _on_background_activated(self, index: int) -> None:
        if self.background_combo.itemData(index) == BackgroundKind.COLOR:
            color = QColorDialog.getColor(QColor(*self._color), self, "Color de fondo")
            if color.isValid():
                self._color = (color.red(), color.green(), color.blue())
                self._emit()

    def _on_favorite(self, index: int) -> None:
        data = self.favorites_combo.itemData(index)
        if data is not None:
            self.apply_favorite(self._favorites[data])

    def _save_favorite(self) -> None:
        unit_label = self.unit_combo.currentText()
        default = (f"{self._display(self._w_mm):g} × {self._display(self._h_mm):g} {unit_label}")
        name, ok = QInputDialog.getText(self, "Guardar formato", "Nombre del formato:",
                                        text=default)
        if ok and name.strip():
            fav = FavoriteFormat(name=name.strip(), width=from_mm(self._w_mm, self._unit),
                                 height=from_mm(self._h_mm, self._unit), unit=self._unit)
            self.favorite_saved.emit(fav)
