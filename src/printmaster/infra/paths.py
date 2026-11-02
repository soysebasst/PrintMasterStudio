"""Ubicaciones de configuración, datos y salida en el PC del usuario."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "PrintMasterStudio"


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _home_override() -> Path | None:
    value = os.environ.get("PRINTMASTER_HOME")
    return Path(value) if value else None


def config_dir() -> Path:
    if (h := _home_override()) is not None:
        return _ensure(h / "config")
    if sys.platform == "win32":
        return _ensure(Path(os.environ.get("APPDATA", Path.home())) / APP_DIR_NAME)
    return _ensure(Path.home() / ".printmaster" / "config")


def data_dir() -> Path:
    if (h := _home_override()) is not None:
        return _ensure(h / "data")
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return _ensure(Path(base) / APP_DIR_NAME)
    return _ensure(Path.home() / ".printmaster" / "data")


def default_output_dir() -> Path:
    if (h := _home_override()) is not None:
        return _ensure(h / "output")
    if sys.platform == "win32":
        return _ensure(Path.home() / "Documents" / "PrintMaster")
    return _ensure(Path.home() / ".printmaster" / "output")
