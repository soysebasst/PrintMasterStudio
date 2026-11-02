"""Mejora con Gemini por la web (gratis, semiautomática): prompt, URL y utilidades."""

from __future__ import annotations

import sys
from pathlib import Path

GEMINI_URL = "https://gemini.google.com/app?hl=es"
ENGINE_GEMINI = "Gemini (web)"
DEFAULT_PROMPT = (
    "Mejora esta imagen para impresión en gran formato. Redibújala en alta resolución, con "
    "bordes nítidos y colores limpios. Conserva exactamente la composición, los colores, los "
    "personajes y TODO el texto tal como está escrito, letra por letra. No agregues ni quites "
    "elementos."
)
ASPECT_TOLERANCE = 0.03


def aspect_mismatch(a: tuple[int, int], b: tuple[int, int], tol: float = ASPECT_TOLERANCE) -> bool:
    ra, rb = a[0] / a[1], b[0] / b[1]
    return abs(ra - rb) / ra > tol


def reveal_command(path: Path) -> list[str]:
    """Comando para mostrar el archivo en el explorador del sistema."""
    path = Path(path)
    if sys.platform == "win32":
        return ["explorer", f"/select,{path}"]
    if sys.platform == "darwin":
        return ["open", "-R", str(path)]
    return ["xdg-open", str(path.parent)]
