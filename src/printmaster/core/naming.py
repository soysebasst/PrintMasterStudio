"""Nombres y carpetas de salida de los PDF."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


@dataclass(frozen=True)
class NamingOptions:
    prefix: str = "Cliente"
    start: int = 1
    digits: int = 3
    use_original_name: bool = False
    by_date: bool = True
    client: str = ""


def sanitize(name: str) -> str:
    """Nombre válido en Windows (sin caracteres prohibidos ni nombres reservados)."""
    clean = _INVALID.sub("", name).strip().rstrip(". ").strip()
    if not clean:
        return "sin_nombre"
    if clean.split(".")[0].upper() in _RESERVED:
        clean += "_"
    return clean


def output_path(base_dir: Path, index: int, src: Path, opts: NamingOptions, today: date) -> Path:
    folder = Path(base_dir)
    if opts.by_date:
        folder /= today.isoformat()
    if opts.client.strip():
        folder /= sanitize(opts.client)
    if opts.use_original_name:
        stem = sanitize(Path(src).stem)
    else:
        stem = f"{sanitize(opts.prefix)}_{opts.start + index:0{opts.digits}d}"
    return folder / f"{stem}.pdf"


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    n = 2
    while True:
        candidate = p.with_name(f"{p.stem}_{n}{p.suffix}")
        if not candidate.exists():
            return candidate
        n += 1
