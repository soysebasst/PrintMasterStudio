"""Envoltorio del ejecutable realesrgan-ncnn-vulkan (aislado en un subproceso)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image

MODEL_PHOTO = "realesrgan-x4plus"
MODEL_ART = "realesrgan-x4plus-anime"
NO_VULKAN_MESSAGE = ("Su equipo no tiene aceleración compatible; se usará la mejora básica "
                     "(más rápida, menos detalle).")
POLL_S = 0.2


class EnhanceError(Exception):
    """Falló la mejora de la imagen."""


class EnhanceCancelled(EnhanceError):
    """El usuario canceló la mejora."""


def exe_name() -> str:
    return "realesrgan-ncnn-vulkan.exe" if sys.platform == "win32" else "realesrgan-ncnn-vulkan"


def _tail(text: str, lines: int = 4) -> str:
    return "\n".join(t for t in text.strip().splitlines()[-lines:])


class RealEsrgan:
    def __init__(self, command: list[str], timeout_s: int = 600) -> None:
        self.command = [str(c) for c in command]
        self.timeout_s = timeout_s

    def upscale_x4(self, src: Path, dst: Path, model: str, tile: int = 0,
                   cancel: threading.Event | None = None) -> None:
        args = self.command + ["-i", str(src), "-o", str(dst), "-n", model, "-s", "4",
                               "-t", str(tile), "-f", "png"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        exe = Path(self.command[-1])
        cwd = exe.parent if exe.exists() else None
        models = exe.parent / "models"
        if models.is_dir():  # ruta explícita: el motor no depende del directorio actual
            args += ["-m", str(models)]
        # stderr a un archivo: el motor imprime progreso y un PIPE lleno lo bloquearía
        with tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=err,
                                        creationflags=flags, cwd=cwd)
            except OSError as exc:
                raise EnhanceError(f"No se pudo iniciar el motor de mejora: {exc}") from exc
            deadline = time.monotonic() + self.timeout_s
            while True:
                try:
                    code = proc.wait(timeout=POLL_S)
                    break
                except subprocess.TimeoutExpired:
                    if cancel is not None and cancel.is_set():
                        proc.kill()
                        proc.wait()
                        raise EnhanceCancelled("Mejora cancelada.") from None
                    if time.monotonic() > deadline:
                        proc.kill()
                        proc.wait()
                        raise EnhanceError("El motor de mejora tardó demasiado.") from None
            err.seek(0)
            stderr = err.read().decode("utf-8", "replace")
        if code != 0 or not Path(dst).exists():
            raise EnhanceError(f"El motor de mejora falló (código {code}). {_tail(stderr)}")

    def self_test(self, tmp_dir: Path) -> tuple[bool, str]:
        tmp_dir = Path(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        src, dst = tmp_dir / "selftest_in.png", tmp_dir / "selftest_out.png"
        Image.new("RGB", (64, 64), (128, 128, 128)).save(src)
        dst.unlink(missing_ok=True)
        try:
            self.upscale_x4(src, dst, MODEL_PHOTO)
            with Image.open(dst) as out:
                if out.size != (256, 256):
                    return False, f"El motor devolvió un tamaño inesperado: {out.size}."
        except EnhanceError as exc:
            text = str(exc).lower()
            if "vk" in text or "vulkan" in text:
                return False, NO_VULKAN_MESSAGE
            return False, str(exc)
        finally:
            for f in (src, dst):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
        return True, "Motor listo"


__all__ = ["EnhanceCancelled", "EnhanceError", "MODEL_ART", "MODEL_PHOTO", "NO_VULKAN_MESSAGE",
           "RealEsrgan", "exe_name"]
