"""Sección «Calidad»: nivel, recomendación, mejora con Gemini web y detalles."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printmaster.core.enhance.enhancer import ENGINE_AI, EnhanceResult
from printmaster.core.image_analyzer import Diagnosis
from printmaster.core.image_loader import SUPPORTED_EXTENSIONS
from printmaster.domain.models import ImageInfo
from printmaster.domain.quality import QualityLevel
from printmaster.ui.icons import icon
from printmaster.ui.widgets.diagnosis_card import DiagnosisCard

SHORT = {
    QualityLevel.EXCELENTE: "Excelente", QualityLevel.BUENA: "Buena",
    QualityLevel.ACEPTABLE: "Aceptable", QualityLevel.BAJA: "Baja",
    QualityLevel.MUY_BAJA: "Muy baja",
}
CHIP_STYLE = {  # fondo, texto
    QualityLevel.EXCELENTE: ("#1b3326", "#7ee787"), QualityLevel.BUENA: ("#1b3326", "#7ee787"),
    QualityLevel.ACEPTABLE: ("#3a3018", "#f0c15a"), QualityLevel.BAJA: ("#3d2a18", "#ffab70"),
    QualityLevel.MUY_BAJA: ("#3d1f22", "#ff8a8a"),
}
WAIT_NAME_CHARS = 26


def _short(name: str | None) -> str:
    """Acorta nombres largos por el medio para que no ensanchen el panel."""
    if name is None or len(name) <= WAIT_NAME_CHARS:
        return name or ""
    half = (WAIT_NAME_CHARS - 1) // 2
    return f"{name[:half]}…{name[-half:]}"


GEMINI_NOTE = "Gemini redibuja la imagen: revise textos, logos y caras antes de aprobar."


class DropZone(QLabel):
    """Zona para soltar (o elegir) la versión mejorada descargada de Gemini."""

    file_dropped = Signal(object)  # Path

    def __init__(self, parent=None) -> None:
        super().__init__("o arrastre aquí la descargada (clic para elegir)", parent)
        self.setObjectName("dropZone")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setWordWrap(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.file_dropped.emit(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        file, _ = QFileDialog.getOpenFileName(self, "Elegir imagen mejorada", "",
                                              f"Imágenes ({exts})")
        if file:
            self.file_dropped.emit(Path(file))


class QualityPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)
        title = QLabel("Calidad")
        title.setObjectName("sectionTitle")
        lay.addWidget(title)
        chip_row = QHBoxLayout()
        self.level_chip = QLabel("—")
        self.level_chip.setObjectName("chip")
        chip_row.addWidget(self.level_chip)
        chip_row.addStretch(1)
        lay.addLayout(chip_row)
        self.recommendation_label = QLabel("")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setObjectName("muted")
        lay.addWidget(self.recommendation_label)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.status_label)
        self.gemini_btn = QPushButton("  Mejorar en Gemini")
        self.gemini_btn.setProperty("primary", True)
        self.gemini_btn.setIcon(icon("sparkles", "#ffffff", 18))
        self.gemini_btn.setToolTip("Copia la imagen al portapapeles para pegarla en Gemini")
        lay.addWidget(self.gemini_btn)
        self.wait_label = QLabel("")
        self.wait_label.setWordWrap(True)
        self.wait_label.setObjectName("muted")
        lay.addWidget(self.wait_label)
        wait_row = QHBoxLayout()
        wait_row.addStretch(1)
        self.copy_prompt_btn = QPushButton("Copiar prompt")
        self.copy_prompt_btn.setObjectName("linkButton")
        wait_row.addWidget(self.copy_prompt_btn)
        self.stop_wait_btn = QPushButton("Dejar de esperar")
        self.stop_wait_btn.setObjectName("linkButton")
        wait_row.addWidget(self.stop_wait_btn)
        lay.addLayout(wait_row)
        self.set_waiting(None)
        self.paste_btn = QPushButton("  Pegar mejorada (Ctrl+V)")
        self.paste_btn.setIcon(icon("clipboard", size=18))
        self.paste_btn.setToolTip("Pega la imagen copiada en Gemini (clic derecho › Copiar imagen)")
        lay.addWidget(self.paste_btn)
        self.drop_zone = DropZone()
        lay.addWidget(self.drop_zone)
        self.note_label = QLabel(GEMINI_NOTE)
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("hint")
        lay.addWidget(self.note_label)
        self.price_card = QFrame()
        self.price_card.setObjectName("card")
        pc = QHBoxLayout(self.price_card)
        pc.setContentsMargins(12, 8, 12, 8)
        col = QVBoxLayout()
        col.setSpacing(0)
        caption = QLabel("Precio sugerido")
        caption.setObjectName("hint")
        col.addWidget(caption)
        self.price_detail = QLabel("")
        self.price_detail.setObjectName("muted")
        col.addWidget(self.price_detail)
        pc.addLayout(col, 1)
        self.price_value = QLabel("")
        self.price_value.setObjectName("priceValue")
        self.price_value.setStyleSheet("color:#7ee7a8; font-size:16pt; font-weight:700;")
        pc.addWidget(self.price_value)
        self.price_card.setVisible(False)
        lay.addWidget(self.price_card)
        self.choice_row = QHBoxLayout()
        lay.addLayout(self.choice_row)
        self.actions_row = QHBoxLayout()
        lay.addLayout(self.actions_row)
        self.details_toggle = QPushButton("▸  Ver detalles")
        self.details_toggle.setObjectName("linkButton")
        self.details_toggle.setCheckable(True)
        self.details_toggle.clicked.connect(self._toggle_details)
        lay.addWidget(self.details_toggle)
        self.details = DiagnosisCard()
        self.details.setVisible(False)
        lay.addWidget(self.details)

    def set_price(self, price_text: str | None, detail: str = "") -> None:
        """Cuadro de precio sugerido de la imagen seleccionada (oculto si no hay)."""
        self.price_card.setVisible(price_text is not None)
        self.price_value.setText(price_text or "")
        self.price_detail.setText(detail)

    def set_waiting(self, name: str | None, *, show_copy_prompt: bool = False) -> None:
        """Muestra u oculta el estado «Esperando descarga de Gemini…»."""
        waiting = name is not None
        self.wait_label.setText(
            f"Esperando descarga de Gemini para «{_short(name)}»…" if waiting else "")
        self.wait_label.setVisible(waiting)
        self.stop_wait_btn.setVisible(waiting)
        self.copy_prompt_btn.setVisible(waiting and show_copy_prompt)

    def _toggle_details(self) -> None:
        open_ = self.details_toggle.isChecked()
        self.details.setVisible(open_)
        self.details_toggle.setText(("▾" if open_ else "▸") + "  Ver detalles")

    def text(self) -> str:
        return "\n".join([self.level_chip.text(), self.recommendation_label.text(),
                          self.status_label.text(), self.details.text()])

    def show_item(self, diag: Diagnosis | None, info: ImageInfo | None, *,
                  price: int | None = None, page_mm: tuple[Decimal, Decimal] | None = None,
                  enhanced: tuple[ImageInfo, EnhanceResult] | None = None,
                  enhancing: bool = False, error: str | None = None,
                  downsample_ppi: int | None = None) -> None:
        if diag is not None:
            bg, fg = CHIP_STYLE[diag.level]
            self.level_chip.setText(f"{SHORT[diag.level]} · {diag.effective_ppi:.0f} PPI")
            self.level_chip.setStyleSheet(f"background:{bg}; color:{fg};")
            self.recommendation_label.setText(
                "Mejorada: compare «Original» y «Mejorada» antes de aprobar."
                if enhanced is not None and not enhancing else diag.recommendation)
        else:
            self.level_chip.setText("Analizando…" if info is not None else "—")
            self.level_chip.setStyleSheet("")
            self.recommendation_label.setText("")
        if enhancing:
            status = '<span style="color:#c9a7ff">✦ Mejorando la imagen…</span>'
        elif enhanced is not None:
            einfo, res = enhanced
            if res.engine.startswith("Gemini"):
                what = f"Mejorada con {res.engine}"
            elif res.engine == ENGINE_AI:
                what = "Mejorada con IA (Real-ESRGAN)"
            else:
                what = "Mejorada (mejora básica)"
            status = (f'<span style="color:#c9a7ff">✦ {what}</span> · '
                      f"{einfo.width_px}×{einfo.height_px} px")
        else:
            status = ""
        if error:
            status += ("<br>" if status else "") + f'<span style="color:#ff8a8a">✕ {error}</span>'
        self.status_label.setText(status)
        self.status_label.setVisible(bool(status))
        has_item = info is not None
        for w in (self.gemini_btn, self.paste_btn, self.drop_zone):
            w.setEnabled(has_item)
        self.details.show_diagnosis(diag, info, downsample_ppi, error, price=price,
                                    page_mm=page_mm, enhanced=enhanced, enhancing=enhancing)

    # compatibilidad con la API de DiagnosisCard
    def show_diagnosis(self, diag, info, downsample_ppi=None, error=None, price=None,
                       page_mm=None, enhanced=None, enhancing=False) -> None:
        self.show_item(diag, info, price=price, page_mm=page_mm, enhanced=enhanced,
                       enhancing=enhancing, error=error, downsample_ppi=downsample_ppi)
