"""Tarjeta con el diagnóstico de la imagen seleccionada."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from printmaster.core.image_analyzer import Diagnosis
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
                       downsample_ppi: int | None = None, error: str | None = None) -> None:
        if info is None:
            self.label.setText(f'<span style="color:#ff6b6b">✕ {error or "Sin datos."}</span>')
            return
        rows = [
            f"<b>Original:</b> {info.width_px}×{info.height_px} px · {info.format} · "
            f"{info.file_size / 1_048_576:.1f} MB",
        ]
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
