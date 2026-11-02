"""Instalación verificada del motor Real-ESRGAN (release oficial)."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from printmaster.core.enhance.realesrgan import EnhanceError, RealEsrgan, exe_name
from printmaster.infra import paths

ENGINE_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
              "realesrgan-ncnn-vulkan-20220424-windows.zip")
ENGINE_SHA256 = "e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96"
CHUNK = 1 << 16


def default_engine_dir() -> Path:
    return paths.data_dir() / "engines" / "realesrgan"


def find_engine(directory: Path | None = None) -> RealEsrgan | None:
    base = Path(directory) if directory is not None else default_engine_dir()
    if not base.is_dir():
        return None
    for candidate in sorted(base.rglob(exe_name())):
        if candidate.is_file() and ".staging" not in candidate.parts:
            return RealEsrgan([str(candidate)])
    return None


def _remove(p: Path) -> None:
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink(missing_ok=True)


def install_engine(
    dest: Path | None = None,
    url: str = ENGINE_URL,
    sha256: str = ENGINE_SHA256,
    opener: Callable[[str], BinaryIO] = urllib.request.urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Descarga, verifica el SHA-256, extrae y activa el motor. Devuelve la ruta del ejecutable."""
    dest = Path(dest) if dest is not None else default_engine_dir()
    dest.mkdir(parents=True, exist_ok=True)
    tmp, staging, current = dest / ".download.zip.tmp", dest / ".staging", dest / "current"
    digest = hashlib.sha256()
    try:
        response = opener(url)
        total = 0
        headers = getattr(response, "headers", None)
        if headers is not None:
            total = int(headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as fh:
            while chunk := response.read(CHUNK):
                fh.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        if digest.hexdigest().lower() != sha256.lower():
            raise EnhanceError("La descarga no coincide con el archivo oficial (hash distinto). "
                               "No se instaló.")
        _remove(staging)
        with zipfile.ZipFile(tmp) as z:
            z.extractall(staging)
        exes = [p for p in staging.rglob(exe_name()) if p.is_file()]
        if not exes:
            raise EnhanceError("El archivo descargado no contiene el motor esperado.")
        _remove(current)
        os.replace(staging, current)
        exe = current / exes[0].relative_to(staging)
        if sys.platform != "win32":
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        return exe
    except EnhanceError:
        raise
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise EnhanceError(f"No se pudo instalar el motor de mejora: {exc}") from exc
    finally:
        _remove(tmp)
        _remove(staging)
