from decimal import Decimal as D
from pathlib import Path

import pytest

from printmaster.core.image_analyzer import Diagnosis
from printmaster.domain.models import FitMode, ImageInfo
from printmaster.domain.quality import QualityLevel
from printmaster.domain.units import Unit
from printmaster.printers.profiles import ValidationIssue
from printmaster.ui.widgets.diagnosis_card import DiagnosisCard
from printmaster.ui.widgets.inspector import Inspector

pytestmark = pytest.mark.ui


@pytest.fixture
def insp(qtbot, settings):
    w = Inspector(settings)
    qtbot.addWidget(w)
    w.show()
    return w


def set_unit(insp, unit):
    insp.unit_combo.setCurrentIndex(insp.unit_combo.findData(unit))


def test_unit_conversion_without_drift(insp):
    insp.set_spec_values(D(600), D(900), Unit.CM)
    assert insp.width_spin.value() == 60 and insp.height_spin.value() == 90
    set_unit(insp, Unit.MM)
    assert insp.width_spin.value() == 600 and insp.height_spin.value() == 900
    set_unit(insp, Unit.IN)
    assert round(insp.width_spin.value(), 2) == 23.62
    assert round(insp.height_spin.value(), 2) == 35.43
    set_unit(insp, Unit.CM)
    set_unit(insp, Unit.IN)
    assert insp.spec().width_mm == D("600")
    assert insp.spec().height_mm == D("900")


def test_user_edit_updates_mm(insp):
    insp.set_spec_values(D(600), D(900), Unit.CM)
    insp.width_spin.setValue(50)
    assert insp.spec().width_mm == D("500")


def test_custom_ppi(insp):
    insp.ppi_combo.setCurrentIndex(insp.ppi_combo.findData(-1))
    assert not insp.ppi_spin.isHidden()
    insp.ppi_spin.setValue(175)
    assert insp.spec().ppi == 175


def test_preset_ppi(insp):
    insp.ppi_combo.setCurrentIndex(insp.ppi_combo.findData(150))
    assert insp.spec().ppi == 150
    assert not insp.ppi_spin.isVisible()


def test_background_only_for_fill(insp):
    insp.mode_combo.setCurrentIndex(insp.mode_combo.findData(FitMode.CONTAIN))
    assert not insp.background_combo.isVisible()
    insp.mode_combo.setCurrentIndex(insp.mode_combo.findData(FitMode.FILL))
    assert insp.background_combo.isVisible()
    assert insp.mode() == FitMode.FILL


def test_issues_label(insp):
    insp.show_issues([ValidationIssue("warning", "rotate",
                                      "El ancho supera 610 mm; gire el formato para imprimir.")])
    assert "gire" in insp.issues_label.text()


def test_changed_debounced(insp, qtbot):
    count = []
    insp.changed.connect(lambda: count.append(1))
    insp.width_spin.setValue(10)
    insp.width_spin.setValue(11)
    insp.width_spin.setValue(12)
    qtbot.wait(400)
    assert len(count) == 1


def test_favorite_applies(insp):
    idx = insp.favorites_combo.findText("60 × 45 cm")
    insp.favorites_combo.setCurrentIndex(idx)
    assert insp.spec().width_mm == D("600") and insp.spec().height_mm == D("450")


def test_diagnosis_card(qtbot):
    card = DiagnosisCard()
    qtbot.addWidget(card)
    diag = Diagnosis(40.0, QualityLevel.MUY_BAJA, QualityLevel.MUY_BAJA, 10.0, 1.0, 1.0, None,
                     ("Pocos píxeles para este tamaño: 40 PPI efectivos.",), "Ampliar")
    info = ImageInfo(Path("a.jpg"), "JPEG", 800, 600, "RGB", False, None, 1, 1000, "")
    card.show_diagnosis(diag, info, downsample_ppi=None)
    text = card.text()
    assert "Muy baja resolución" in text and "PPI" in text and "800×600" in text
    card.show_diagnosis(diag, info, downsample_ppi=200)
    assert "Se reducirá a 200 PPI" in card.text()


def test_defaults_fit_length_60(insp):
    assert insp.mode() == FitMode.FIT_LENGTH
    assert insp.spec().width_mm == D(600)


def test_height_editable_in_fit_length(insp):  # 2E: escribir el largo pasa a «Recortar»
    assert not insp.height_spin.isReadOnly()
    insp.height_spin.setValue(55.0)
    assert insp.mode() == FitMode.COVER and insp.spec().height_mm == D(550)


def test_calculated_length(insp):
    insp.set_calculated_length(D(1100))
    assert insp.height_spin.value() == 110
    assert "auto" in insp.height_spin.suffix()


def test_enhance_choice_signal(insp, qtbot):
    from printmaster.domain.models import EnhanceChoice
    with qtbot.waitSignal(insp.enhance_choice_changed) as blocker:
        insp.enhance_combo.setCurrentIndex(insp.enhance_combo.findData(EnhanceChoice.OFF))
    assert blocker.args == [EnhanceChoice.OFF]


def test_card_price_and_enhanced(qtbot):
    from printmaster.core.enhance.enhancer import EnhanceResult
    card = DiagnosisCard()
    qtbot.addWidget(card)
    diag = Diagnosis(160.0, QualityLevel.ACEPTABLE, QualityLevel.ACEPTABLE, 10.0, 1.0, 1.0, None,
                     (), "Conservar la imagen original.")
    info = ImageInfo(Path("a.jpg"), "JPEG", 236, 420, "RGB", False, None, 1, 1000, "")
    einfo = ImageInfo(Path("e.png"), "PNG", 3776, 6720, "RGB", False, None, 1, 1000, "")
    res = EnhanceResult(Path("e.png"), "realesrgan-x4plus-anime", 2, "Real-ESRGAN")
    card.show_diagnosis(diag, info, price=17000, page_mm=(D(600), D(1100)),
                        enhanced=(einfo, res))
    t = card.text()
    assert "60 × 110 cm" in t and "$17.000" in t
    assert "Mejorada con IA" in t and "3776×6720" in t
    assert "alta resolución" not in t.lower()
    card.show_diagnosis(diag, info, enhancing=True)
    assert "Mejorando la imagen" in card.text()
