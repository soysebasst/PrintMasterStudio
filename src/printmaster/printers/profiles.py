"""Perfiles de impresora y validación del formato de impresión."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from importlib import resources
from typing import Literal

from printmaster.domain.models import PrintSpec


@dataclass(frozen=True)
class PrinterProfile:
    id: str
    name: str
    roll_min_mm: Decimal
    roll_max_mm: Decimal
    sheet_min_mm: Decimal
    sheet_max_mm: Decimal
    side_margin_mm: Decimal
    max_length_mm: Decimal


@dataclass(frozen=True)
class ValidationIssue:
    level: Literal["error", "warning"]
    code: str
    message: str


_DECIMAL_FIELDS = (
    "roll_min_mm", "roll_max_mm", "sheet_min_mm", "sheet_max_mm",
    "side_margin_mm", "max_length_mm",
)


def _from_dict(data: dict) -> PrinterProfile:
    values = {k: Decimal(str(data[k])) for k in _DECIMAL_FIELDS}
    return PrinterProfile(id=data["id"], name=data["name"], **values)


def list_profiles() -> list[PrinterProfile]:
    folder = resources.files("printmaster.printers")
    profiles = []
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".json"):
            profiles.append(_from_dict(json.loads(entry.read_text(encoding="utf-8"))))
    return profiles


def load_profile(profile_id: str = "epson_sc_t3170") -> PrinterProfile:
    for profile in list_profiles():
        if profile.id == profile_id:
            return profile
    raise KeyError(f"Perfil de impresora desconocido: {profile_id}")


def _fmt(d: Decimal) -> str:
    return f"{d.normalize():f}"


def validate(spec: PrintSpec, profile: PrinterProfile) -> list[ValidationIssue]:
    """Valida un formato ya orientado: el ancho es lo que cruza el rollo."""
    w, h = spec.width_mm, spec.height_mm
    roll = profile.roll_max_mm
    if w <= 0 or h <= 0:
        return [ValidationIssue("error", "invalid",
                                "Las dimensiones deben ser mayores que cero.")]
    issues: list[ValidationIssue] = []
    if w > roll and h > roll:
        issues.append(ValidationIssue(
            "error", "too_wide",
            f"Ningún lado cabe en la impresora (máx. {_fmt(roll)} mm de ancho)."))
        return issues
    if w > roll:
        issues.append(ValidationIssue(
            "warning", "rotate",
            f"El ancho supera {_fmt(roll)} mm; gire el formato para imprimir."))
    if h > profile.max_length_mm:
        issues.append(ValidationIssue(
            "error", "too_long",
            f"El largo supera {_fmt(profile.max_length_mm)} mm, el máximo de un PDF."))
    if roll - 2 * profile.side_margin_mm < w <= roll:
        issues.append(ValidationIssue(
            "warning", "margin",
            f"El diseño invade los márgenes físicos de "
            f"{_fmt(profile.side_margin_mm)} mm del rollo."))
    return issues
