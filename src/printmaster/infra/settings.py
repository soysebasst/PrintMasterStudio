"""Configuración persistente del usuario (JSON validado con pydantic)."""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from printmaster.core.pricing import PricingConfig
from printmaster.domain.models import FitMode, Orientation
from printmaster.domain.units import Unit
from printmaster.infra import paths

log = logging.getLogger("printmaster")


class FavoriteFormat(BaseModel):
    name: str
    width: Decimal
    height: Decimal
    unit: Unit = Unit.CM


def _default_favorites() -> list[FavoriteFormat]:
    sizes = [(60, 30), (60, 45), (60, 60), (60, 90), (60, 120), (60, 150)]
    return [FavoriteFormat(name=f"{w} × {h} cm", width=Decimal(w), height=Decimal(h))
            for w, h in sizes]


SETTINGS_VERSION = 2


class Settings(BaseModel):
    settings_version: int = SETTINGS_VERSION
    output_dir: Path = Field(default_factory=paths.default_output_dir)
    default_ppi: int = Field(200, ge=50, le=600)
    default_unit: Unit = Unit.CM
    default_mode: FitMode = FitMode.FIT_LENGTH
    default_orientation: Orientation = Orientation.AS_ENTERED
    roll_width_mm: int = Field(600, ge=210, le=610)
    length_step_mm: int = Field(50, ge=1, le=500)
    price_short: int = Field(10000, ge=0)
    price_long: int = Field(15000, ge=0)
    ref_short_mm: int = Field(450, ge=1)
    ref_long_mm: int = Field(900, ge=2)
    min_price: int = Field(10000, ge=0)
    price_round_to: int = Field(1000, ge=1)
    enhance_enabled: bool = True
    enhance_target_ppi: int = Field(150, ge=72, le=300)
    printer_id: str = "epson_sc_t3170"
    naming_prefix: str = "Cliente"
    naming_digits: int = Field(3, ge=1, le=8)
    naming_by_date: bool = True
    favorites: list[FavoriteFormat] = Field(default_factory=_default_favorites)

    def pricing(self) -> PricingConfig:
        return PricingConfig(
            ref_short_mm=self.ref_short_mm, price_short=self.price_short,
            ref_long_mm=self.ref_long_mm, price_long=self.price_long,
            min_price=self.min_price, round_to=self.price_round_to,
            base_width_mm=600,
        )


def _migrate(data: dict) -> dict:
    """Configuración de la Fase 1 (sin versión): modo largo automático y orientación fija."""
    if int(data.get("settings_version", 1)) < 2:
        data["default_mode"] = FitMode.FIT_LENGTH.value
        data["default_orientation"] = Orientation.AS_ENTERED.value
        data["settings_version"] = SETTINGS_VERSION
    return data


def _default_path() -> Path:
    return paths.config_dir() / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or _default_path()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("formato inesperado")
        return Settings.model_validate(_migrate(data))
    except (ValidationError, ValueError, OSError) as exc:
        backup = path.with_name(path.name + ".bak")
        try:
            os.replace(path, backup)
        except OSError:
            pass
        log.warning("Configuración inválida; se restauraron los valores por defecto (%s)", exc)
        return Settings()


def save_settings(s: Settings, path: Path | None = None) -> None:
    path = path or _default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(s.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
