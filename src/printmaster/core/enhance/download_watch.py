"""Vigila la carpeta de descargas para recibir la imagen mejorada en Gemini."""

from __future__ import annotations

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
            entries = list(self.folder.iterdir())
        except OSError:
            return []
        for p in entries:
            name = p.name.lower()
            if name.endswith(PARTIAL_SUFFIXES) or p.suffix.lower() not in self.exts:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size > 0 and st.st_mtime >= self.since and p.is_file():
                found.append((st.st_mtime, p, st.st_size))
        return sorted(found, reverse=True)

    def poll(self) -> Path | None:
        if not self.folder_ok:
            return None
        result = None
        sizes: dict[Path, int] = {}
        for _mtime, path, size in self._candidates():
            sizes[path] = size
            if result is None and self._sizes.get(path) == size:
                result = path
        self._sizes = sizes
        return result
