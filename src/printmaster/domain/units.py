"""Conversión de unidades físicas. Internamente todo se expresa en mm (Decimal)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MM_PER_INCH = Decimal("25.4")
PT_PER_INCH = Decimal(72)


class Unit(StrEnum):
    MM = "mm"
    CM = "cm"
    IN = "in"


_FACTOR_TO_MM = {Unit.MM: Decimal(1), Unit.CM: Decimal(10), Unit.IN: MM_PER_INCH}


def _dec(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def to_mm(value: Decimal | int | float | str, unit: Unit) -> Decimal:
    return _dec(value) * _FACTOR_TO_MM[Unit(unit)]


def from_mm(mm: Decimal, unit: Unit) -> Decimal:
    result = _dec(mm) / _FACTOR_TO_MM[Unit(unit)]
    return result.normalize() if result == result.to_integral_value() else result


def mm_to_pt(mm: Decimal) -> float:
    return float(_dec(mm) * PT_PER_INCH / MM_PER_INCH)


def mm_to_px(mm: Decimal, ppi: int) -> int:
    px = _dec(mm) / MM_PER_INCH * Decimal(ppi)
    return int(px.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def effective_ppi(px: int, mm: Decimal) -> float:
    inches = _dec(mm) / MM_PER_INCH
    return float(Decimal(px) / inches) if inches > 0 else 0.0
