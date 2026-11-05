"""Precio sugerido por lámina (interpolación lineal entre dos precios de referencia)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class PricingConfig:
    ref_short_mm: int = 450
    price_short: int = 10000
    ref_long_mm: int = 900
    price_long: int = 15000
    min_price: int = 10000
    round_to: int = 1000
    base_width_mm: int = 600


def suggest_price(width_mm: Decimal, length_mm: Decimal,
                  cfg: PricingConfig = PricingConfig()) -> int:
    """Precio sugerido. Para anchos distintos del base se escala por área."""
    eq = Decimal(length_mm) * Decimal(width_mm) / Decimal(cfg.base_width_mm)
    slope = Decimal(cfg.price_long - cfg.price_short) / Decimal(cfg.ref_long_mm - cfg.ref_short_mm)
    raw = Decimal(cfg.price_short) + (eq - Decimal(cfg.ref_short_mm)) * slope
    step = Decimal(cfg.round_to)
    rounded = (raw / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
    return max(cfg.min_price, int(rounded))


def billable_length_mm(length_mm: Decimal, step_mm: int = 50) -> Decimal:
    """Largo que se cobra: la lámina mide lo justo, pero se cobra por tramos (5 cm)."""
    steps = math.ceil(float(Decimal(length_mm) / Decimal(step_mm)) - 1e-9)
    return Decimal(max(1, steps) * step_mm)


def format_cop(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")
