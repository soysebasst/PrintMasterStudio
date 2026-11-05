"""Inspector de formato: tamaño físico, unidades, orientación, PPI, modo de ajuste y fondo."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from printmaster.core.pricing import format_cop
from printmaster.domain.models import (
    Background,
    BackgroundKind,
    EnhanceChoice,
    FitMode,
    Orientation,
    PrintSpec,
)
from printmaster.domain.units import Unit, from_mm, to_mm
from printmaster.infra.settings import FavoriteFormat, Settings, load_settings, save_settings
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


ENHANCE_LABELS = [
    (EnhanceChoice.AUTO, "Mejora: Automática"),
    (EnhanceChoice.ON, "Mejorar con IA"),
    (EnhanceChoice.OFF, "No mejorar"),
]


class Inspector(QWidget):
    changed = Signal()
    favorite_saved = Signal(object)  # FavoriteFormat
    enhance_choice_changed = Signal(object)  # EnhanceChoice

    def __init__(self, settings: Settings, parent=None, *, print_options: bool = True) -> None:
        """print_options=False: la resolución y la orientación quedan solo en Configuración
        (la ventana principal usa la resolución por defecto y gira la imagen, no la lámina)."""
        super().__init__(parent)
        self._print_options = print_options
        self._w_mm = Decimal(settings.roll_width_mm)
        self._h_mm = Decimal(900)
        self._unit = Unit(settings.default_unit)
        self._color: tuple[int, int, int] = (255, 255, 255)
        self._favorites: list[FavoriteFormat] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.changed.emit)

        self._settings = settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        def section(title: str) -> QLabel:
            lbl = QLabel(title)
            lbl.setObjectName("sectionTitle")
            return lbl

        # --- Tamaño -------------------------------------------------------------------
        title_row = QHBoxLayout()
        title_row.addWidget(section("Tamaño"))
        self.favorites_combo = QComboBox()
        self.favorites_combo.setObjectName("favorites_combo")
        self.favorites_combo.setToolTip("Formatos favoritos")
        title_row.addWidget(self.favorites_combo, 1)
        lay.addLayout(title_row)
        size_row = QHBoxLayout()
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setObjectName("width_spin")
        self.width_spin.setToolTip("Ancho")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setObjectName("height_spin")
        self.height_spin.setToolTip("Largo")
        for spin in (self.width_spin, self.height_spin):
            spin.setMinimumWidth(56)
            spin.setRange(0.1, 10000)
            spin.setDecimals(2)
            spin.setKeyboardTracking(False)
        self.unit_combo = QComboBox()
        self.unit_combo.setObjectName("unit_combo")
        for unit, label in ((Unit.CM, "cm"), (Unit.MM, "mm"), (Unit.IN, "pulgadas")):
            self.unit_combo.addItem(label, unit)
        self.unit_combo.setMaximumWidth(92)
        times = QLabel("×")
        size_row.addWidget(self.width_spin, 3)
        size_row.addWidget(times)
        size_row.addWidget(self.height_spin, 4)
        size_row.addWidget(self.unit_combo, 2)
        lay.addLayout(size_row)
        self.price_label = QLabel("")
        self.price_label.setObjectName("priceLabel")
        lay.addWidget(self.price_label)
        self.issues_label = QLabel("")
        self.issues_label.setObjectName("issues_label")
        self.issues_label.setWordWrap(True)
        self.issues_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.issues_label)

        # --- Ajuste -------------------------------------------------------------------
        lay.addWidget(section("Ajuste"))
        self.mode_combo = QComboBox()  # modelo interno; se maneja con los botones
        self.mode_combo.setObjectName("mode_combo")
        for mode, label in MODE_LABELS:
            self.mode_combo.addItem(label, mode)
        self.mode_combo.setVisible(False)
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        short = {FitMode.FIT_LENGTH: "Largo auto", FitMode.CONTAIN: "Ajustar",
                 FitMode.FILL: "Rellenar", FitMode.COVER: "Recortar"}
        self.mode_buttons: dict[FitMode, QPushButton] = {}
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for k, (mode, label) in enumerate(MODE_LABELS):
            btn = QPushButton(short[mode])
            btn.setObjectName("segment")
            btn.setMinimumWidth(60)
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.clicked.connect(lambda _c=False, m=mode: self._select_mode(m))
            self._mode_group.addButton(btn)
            self.mode_buttons[mode] = btn
            grid.addWidget(btn, k // 2, k % 2)
        lay.addLayout(grid)
        bg_row = QHBoxLayout()
        self.background_label = QLabel("Fondo:")
        self.background_combo = QComboBox()
        self.background_combo.setObjectName("background_combo")
        for kind, label in BACKGROUND_LABELS:
            self.background_combo.addItem(label, kind)
        bg_row.addWidget(self.background_label)
        bg_row.addWidget(self.background_combo, 1)
        lay.addLayout(bg_row)

        # --- Calidad (la inserta la página) -------------------------------------------
        self._quality_index = lay.count()
        self.enhance_combo = QComboBox()
        self.enhance_combo.setObjectName("enhance_combo")
        for choice, label in ENHANCE_LABELS:
            self.enhance_combo.addItem(label, choice)
        self.enhance_combo.setToolTip("Mejora local de la imagen seleccionada")

        # --- Opciones avanzadas -------------------------------------------------------
        self.advanced_toggle = QPushButton("▸  Opciones avanzadas")
        self.advanced_toggle.setObjectName("linkButton")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)
        self.toggles_row = QHBoxLayout()
        self.toggles_row.addStretch(1)
        self.toggles_row.addWidget(self.advanced_toggle)
        lay.addLayout(self.toggles_row)
        self.advanced_box = QWidget()
        adv = QFormLayout(self.advanced_box)
        adv.setContentsMargins(0, 0, 0, 0)
        self.orientation_combo = QComboBox()
        self.orientation_combo.setObjectName("orientation_combo")
        for o, label in ((Orientation.AS_ENTERED, "Como se escribió"),
                         (Orientation.AUTO, "Automática"), (Orientation.PORTRAIT, "Vertical"),
                         (Orientation.LANDSCAPE, "Horizontal")):
            self.orientation_combo.addItem(label, o)
        adv.addRow("Orientación:", self.orientation_combo)
        self.ppi_combo = QComboBox()
        self.ppi_combo.setObjectName("ppi_combo")
        for ppi in PPI_PRESETS:
            self.ppi_combo.addItem(f"{ppi} PPI", ppi)
        self.ppi_combo.addItem("Personalizado…", CUSTOM_PPI)
        adv.addRow("Resolución:", self.ppi_combo)
        self.ppi_spin = QSpinBox()
        self.ppi_spin.setObjectName("ppi_spin")
        self.ppi_spin.setRange(50, 600)
        self.ppi_spin.setSuffix(" PPI")
        self.ppi_spin.setKeyboardTracking(False)
        adv.addRow("", self.ppi_spin)
        if not print_options:
            for w in (self.orientation_combo, self.ppi_combo, self.ppi_spin):
                adv.setRowVisible(w, False)
        self.lossless_check = QCheckBox("Exportar sin pérdida")
        self.lossless_check.setObjectName("lossless_check")
        self.lossless_check.setChecked(True)
        self.lossless_check.setToolTip(
            "Desactivado: las fotos JPEG que deban reducirse se guardan como JPEG de calidad 95.")
        adv.addRow("", self.lossless_check)
        self.save_favorite_btn = QPushButton("★ Guardar formato como favorito")
        self.save_favorite_btn.setObjectName("save_favorite_btn")
        adv.addRow("", self.save_favorite_btn)
        lay.addWidget(self.advanced_box)
        self._set_advanced(bool(getattr(settings, "advanced_open", False)), save=False)
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
        self.enhance_combo.currentIndexChanged.connect(
            lambda _i: self.enhance_choice_changed.emit(
                EnhanceChoice(self.enhance_combo.currentData())))

    # --- API ------------------------------------------------------------------------
    def spec(self) -> PrintSpec:
        orientation = (Orientation(self.orientation_combo.currentData()) if self._print_options
                       else Orientation.AS_ENTERED)
        return PrintSpec(self._w_mm, self._h_mm, self.ppi(), orientation)

    def set_default_ppi(self, ppi: int) -> None:
        """Resolución que viene de Configuración."""
        preset = self.ppi_combo.findData(ppi)
        self.ppi_combo.blockSignals(True)
        self.ppi_combo.setCurrentIndex(preset if preset >= 0 else
                                       self.ppi_combo.findData(CUSTOM_PPI))
        self.ppi_combo.blockSignals(False)
        self.ppi_spin.blockSignals(True)
        self.ppi_spin.setValue(ppi)
        self.ppi_spin.blockSignals(False)
        self._update_visibility()
        self._emit()

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

    def quality_insert_index(self) -> int:
        return self._quality_index

    def set_price(self, price: int | None) -> None:
        self.price_label.setText(f"{format_cop(price)} sugerido" if price is not None else "")

    def _select_mode(self, mode: FitMode) -> None:
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(mode))

    def _sync_mode_buttons(self) -> None:
        current = self.mode_combo.currentData()
        for mode, btn in self.mode_buttons.items():
            btn.setChecked(mode == current)

    def _set_advanced(self, open_: bool, save: bool = True) -> None:
        self.advanced_toggle.setChecked(open_)
        self.advanced_toggle.setText(("▾" if open_ else "▸") + "  Opciones avanzadas")
        self.advanced_box.setVisible(open_)
        if save and getattr(self._settings, "advanced_open", None) != open_:
            self._settings.advanced_open = open_
            disk = load_settings()  # solo este campo: no pisar lo guardado en Configuración
            disk.advanced_open = open_
            save_settings(disk)

    def _toggle_advanced(self) -> None:
        self._set_advanced(self.advanced_toggle.isChecked())

    def set_calculated_length(self, mm: Decimal | None) -> None:
        """Largo calculado por el modo automático para la imagen actual (solo lectura)."""
        if mm is None or self.mode() != FitMode.FIT_LENGTH:
            return
        self.height_spin.blockSignals(True)
        self.height_spin.setValue(self._display(Decimal(mm)))
        self.height_spin.blockSignals(False)
        self.height_spin.lineEdit().setCursorPosition(0)  # que se vea el número, no el final

    def set_enhance_choice(self, choice: EnhanceChoice) -> None:
        self.enhance_combo.blockSignals(True)
        self.enhance_combo.setCurrentIndex(self.enhance_combo.findData(choice))
        self.enhance_combo.blockSignals(False)

    def show_issues(self, issues: list[ValidationIssue]) -> None:
        parts = []
        for issue in issues:
            color = "#ff6b6b" if issue.level == "error" else "#f0b429"
            icon = "✕" if issue.level == "error" else "▲"
            parts.append(f'<span style="color:{color}">{icon} {issue.message}</span>')
        self.issues_label.setText("<br>".join(parts))
        self.issues_label.setVisible(bool(parts))

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
        if self.mode() == FitMode.FIT_LENGTH:
            # escribir un largo: la imagen llena esa lámina y se arrastra qué parte se corta
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(FitMode.COVER))
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
        self._sync_mode_buttons()
        self.ppi_spin.setVisible(self._print_options
                                 and self.ppi_combo.currentData() == CUSTOM_PPI)
        fill = self.mode_combo.currentData() == FitMode.FILL
        self.background_combo.setVisible(fill)
        self.background_label.setVisible(fill)
        auto = self.mode_combo.currentData() == FitMode.FIT_LENGTH
        self.height_spin.setReadOnly(False)  # 2E: también se puede escribir en «Largo auto»
        self.height_spin.setSuffix(" auto" if auto else "")
        if not auto:
            self._refresh_spins()

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
