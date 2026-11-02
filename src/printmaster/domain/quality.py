"""Clasificación de calidad según el PPI efectivo de impresión."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QualityLevel(Enum):
    EXCELENTE = "Excelente"
    BUENA = "Buena"
    ACEPTABLE = "Aceptable"
    BAJA = "Baja resolución"
    MUY_BAJA = "Muy baja resolución"


_ORDER = [
    QualityLevel.EXCELENTE,
    QualityLevel.BUENA,
    QualityLevel.ACEPTABLE,
    QualityLevel.BAJA,
    QualityLevel.MUY_BAJA,
]


@dataclass(frozen=True)
class QualityThresholds:
    excelente: float = 250
    buena: float = 180
    aceptable: float = 120
    baja: float = 72


DEFAULT_THRESHOLDS = QualityThresholds()


def classify(ppi: float, t: QualityThresholds = DEFAULT_THRESHOLDS) -> QualityLevel:
    if ppi >= t.excelente:
        return QualityLevel.EXCELENTE
    if ppi >= t.buena:
        return QualityLevel.BUENA
    if ppi >= t.aceptable:
        return QualityLevel.ACEPTABLE
    if ppi >= t.baja:
        return QualityLevel.BAJA
    return QualityLevel.MUY_BAJA


def downgrade(level: QualityLevel) -> QualityLevel:
    i = _ORDER.index(level)
    return _ORDER[min(i + 1, len(_ORDER) - 1)]
