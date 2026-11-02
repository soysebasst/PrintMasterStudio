"""Tarjeta con el diagnóstico de la imagen seleccionada."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from printmaster.core.enhance.enhancer import EnhanceResult
from printmaster.core.image_analyzer import Diagnosis
from printmaster.core.pricing import format_cop
from printmaster.domain.models import ImageInfo
from printmaster.domain.quality import QualityLevel

LEVEL_COLORS = {
    QualityLevel.EXCELENTE: "#2e9d5b",
    QualityLevel.BUENA: "#4caf50",
    QualityLevel.ACEPTABLE: "#c9a227",
    QualityLevel.BAJA: "#e07b24",
    QualityLevel.MUY_BAJA: "#d64545",
}


class DiagnosisCard(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__("DIAGNÓSTICO", parent)
        lay = QVBoxLayout(self)
        self.label = QLabel("Seleccione una imagen.")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        lay.addWidget(self.label)

    def text(self) -> str:
        return self.label.text()

    def show_diagnosis(self, diag: Diagnosis | None, info: ImageInfo | None,
                       downsample_ppi: int | None = None, error: str | None = None,
                       price: int | None = None,
                       page_mm: tuple[Decimal, Decimal] | None = None,
                       enhanced: tuple[ImageInfo, EnhanceResult] | None = None,
                       enhancing: bool = False) -> None:
        if info is None:
            self.label.setText(f'<span style="color:#ff6b6b">✕ {error or "Sin datos."}</span>')
            return
        rows = [
            f"<b>Original:</b> {info.width_px}×{info.height_px} px · {info.format} · "
            f"{info.file_size / 1_048_576:.1f} MB",
        ]
        if page_mm is not None:
            w, h = (f"{(v / 10).normalize():f}".replace(".", ",") for v in page_mm)
            line = f"<b>Lámina:</b> {w} × {h} cm"
            if price is not None:
                line += (' · <b>Precio sugerido:</b> '
                         f'<span style="color:#7ee787">{format_cop(price)}</span>')
            rows.append(line)
        if enhancing:
            rows.append('<span style="color:#c39bd3">✦ Mejorando la imagen…</span>')
        elif enhanced is not None:
            einfo, res = enhanced
            if res.engine.startswith("Gemini"):
                detail = f"Mejorada con {res.engine}"
            elif res.engine == "Real-ESRGAN":
                detail = f"Mejorada con IA (Real-ESRGAN, {res.passes} pasada" \
                         f"{'s' if res.passes != 1 else ''})"
            else:
                detail = f"Mejorada ({res.engine}, {res.passes} pasada" \
                         f"{'s' if res.passes != 1 else ''})"
            rows.append(f'<span style="color:#c39bd3">✦ {detail}: '
                        f"{einfo.width_px}×{einfo.height_px} px</span>")
        if error:
            rows.append(f'<span style="color:#ff6b6b">✕ {error}</span>')
        if diag is None:
            rows.append("<i>Analizando…</i>")
            self.label.setText("<br>".join(rows))
            return
        color = LEVEL_COLORS[diag.level]
        rows.append(f"<b>PPI efectivo:</b> {diag.effective_ppi:.0f} PPI")
        rows.append(f'<b>Calidad:</b> <span style="color:{color}; font-weight:bold">'
                    f"{diag.level.value}</span>")
        rows.append(f"<b>Nitidez:</b> {diag.sharpness:.1f} · <b>Ruido:</b> "
                    f"{diag.noise_sigma:.1f}")
        if diag.jpeg_quality is not None:
            rows.append(f"<b>Calidad JPEG estimada:</b> {diag.jpeg_quality}")
        if downsample_ppi is not None:
            rows.append(f"Se reducirá a {downsample_ppi} PPI (archivo más liviano).")
        for w in diag.warnings:
            rows.append(f'<span style="color:#f0b429">▲ {w}</span>')
        rows.append(f"<b>Recomendación:</b> {diag.recommendation}")
        self.label.setText("<br>".join(rows))
