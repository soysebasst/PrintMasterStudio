"""Vigila la carpeta de descargas para recibir la imagen mejorada en Gemini."""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path

from printmaster.core.image_loader import SUPPORTED_EXTENSIONS

PARTIAL_SUFFIXES = (".crdownload", ".part", ".tmp", ".download")


class DownloadWatch:
    """Devuelve la imagen más reciente descargada después de `since`, ya completa.

    Una descarga se considera completa cuando su tamaño no cambió entre dos sondeos.
    Nunca mueve ni modifica archivos.
    """

    def __init__(self, folder: Path, since: float,
                 exts: frozenset[str] = SUPPORTED_EXTENSIONS) -> None:
        self.folder = Path(folder)
        self.since = since
        self.exts = exts
        self._sizes: dict[Path, int] = {}

    @property
    def folder_ok(self) -> bool:
        return self.folder.is_dir()

    def _candidates(self) -> list[tuple[float, Path, int]]:
        found = []
        try:
            with os.scandir(self.folder) as it:  # stat en caché en Windows: barato cada segundo
                entries = list(it)
        except OSError:
            return []
        for entry in entries:
            name = entry.name.lower()
            if name.endswith(PARTIAL_SUFFIXES) or Path(name).suffix not in self.exts:
                continue
            try:
                if not entry.is_file():
                    continue
                st = entry.stat()
            except OSError:
                continue
            if st.st_size > 0 and st.st_mtime >= self.since:
                found.append((st.st_mtime, Path(entry.path), st.st_size))
        return sorted(found, reverse=True)

    def poll(self, exclude: Collection[Path] = (), oldest: bool = False) -> Path | None:
        """La imagen nueva y completa más reciente (u, con `oldest`, la más antigua).

        `exclude` son archivos ya usados que no deben devolverse otra vez.
        """
        if not self.folder_ok:
            return None
        stable = []
        sizes: dict[Path, int] = {}
        for _mtime, path, size in self._candidates():
            sizes[path] = size
            if path not in exclude and self._sizes.get(path) == size:
                stable.append(path)
        self._sizes = sizes
        if not stable:
            return None
        return stable[-1] if oldest else stable[0]
