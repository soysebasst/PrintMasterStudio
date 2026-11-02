"""Texto de la barra inferior: qué debe hacer el usuario a continuación."""

from __future__ import annotations

from printmaster.app_services.job_controller import JobController
from printmaster.domain.models import ItemStatus
from printmaster.domain.quality import QualityLevel

_LOW = (QualityLevel.BAJA, QualityLevel.MUY_BAJA)


def next_step(ctrl: JobController, analyzing: bool, enhancing: bool) -> str:
    items = [it for it in ctrl.items if it.status != ItemStatus.ERROR]
    if not ctrl.items:
        return "Arrastra o agrega las imágenes del cliente"
    if analyzing:
        return "Analizando imágenes…"
    if enhancing:
        return "Mejorando imágenes…"
    if ctrl.exportable_indices():
        return "Exporta los PDF"
    if items and all(it.status == ItemStatus.EXPORTED for it in items):
        return "Listo. Abre la carpeta de salida"
    for it in items:
        if (it.status == ItemStatus.READY and it.diagnosis is not None
                and it.diagnosis.level in _LOW and not it.uses_enhanced):
            return f"Mejora «{it.path.name}» con Gemini o apruébala tal cual"
    if any(it.status == ItemStatus.READY for it in items):
        return "Revisa la vista previa y pulsa Aprobar todo"
    if not items:
        return "Quita las imágenes con error o agrega otras"
    return "Analizando imágenes…"
