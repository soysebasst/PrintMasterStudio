"""Configuración persistente del usuario (JSON validado con pydantic)."""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from printmaster.domain.models import FitMode
from printmaster.domain.units import Unit
from printmaster.infra import paths

log = logging.getLogger("printmaster")


class FavoriteFormat(BaseModel):
    name: str
    width: Decimal
    height: Decimal
    unit: Unit = Unit.CM


def _default_favorites() -> list[FavoriteFormat]:
    sizes = [(60, 45), (60, 90), (60, 120), (50, 70), (40, 60), (60, 150)]
    return [FavoriteFormat(name=f"{w} × {h} cm", width=Decimal(w), height=Decimal(h))
            for w, h in sizes]


class Settings(BaseModel):
    output_dir: Path = Field(default_factory=paths.default_output_dir)
    default_ppi: int = Field(200, ge=50, le=600)
    default_unit: Unit = Unit.CM
    default_mode: FitMode = FitMode.CONTAIN
    printer_id: str = "epson_sc_t3170"
    naming_prefix: str = "Cliente"
    naming_digits: int = Field(3, ge=1, le=8)
    naming_by_date: bool = True
    favorites: list[FavoriteFormat] = Field(default_factory=_default_favorites)


def _default_path() -> Path:
    return paths.config_dir() / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or _default_path()
    if not path.exists():
        return Settings()
    try:
        return Settings.model_validate_json(path.read_text(encoding="utf-8"))
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
