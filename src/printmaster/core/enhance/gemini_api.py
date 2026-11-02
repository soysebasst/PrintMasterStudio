"""Gemini por API (opción B): solo la interfaz; se implementará en una fase futura.

Requiere una API Key de Google AI Studio con facturación: la API no tiene nivel gratuito para
modelos de imagen. No se hace ninguna llamada de red desde este módulo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class GeminiEnhancer(Protocol):
    def enhance(self, src: Path, prompt: str) -> Path:
        """Envía la imagen a Gemini y devuelve la ruta del resultado (PNG)."""
        ...


API_AVAILABLE = False
API_NOTE = ("Gemini por API: disponible en una versión futura "
            "(requiere API Key con facturación).")
