# Registro de avance — PrintMaster Studio

## Hecho
- Especificación aprobada (`docs/superpowers/specs/2026-11-02-printmaster-studio-design.md`)
- Plan Fase 1 (`docs/superpowers/plans/2026-11-02-fase1-app-basica.md`)
- Fase 1: dominio, perfiles de impresora, carga, ajuste, color, PDF, nombres, diagnóstico,
  configuración, controlador de trabajo e interfaz (Inicio, Nuevo trabajo, Configuración)

## Fase 1 — implementada (pendiente de validación en Windows)
- Tareas 1–16 completas con pruebas (`pytest -q`, 159 pruebas)
- Checklist para validar en el PC: `docs/acceptance/fase1-checklist.md`
- **No se considera cerrada hasta que Camilo confirme el checklist.**

## Fase 2A — implementada (pendiente de validación en Windows)
- Lámina con ancho fijo de 60 cm y largo automático (de 5 en 5 cm)
- Precio sugerido por lámina y total del lote ($10.000 por 60×45, $15.000 por 60×90, mínimo $10.000)
- Mejora local con Real-ESRGAN (instalador verificado, respaldo básico sin IA, caché, antes/después)
- Checklist: `docs/acceptance/aceptacion.md` (sección Fase 2A)

## Fase 2B — implementada (pendiente de validación en Windows)
- Mejora con Gemini por la web (gratis): copiar prompt, abrir Gemini, soltar el resultado
- Interfaz rediseñada: tarjetas, pasos, «Siguiente:», panel corto con opciones avanzadas plegadas
- Acceso directo con doble clic (`crear_acceso_directo.bat`), sin consola
- Gemini por API: interfaz preparada, sin activar (requiere facturación)

## Fase 2C — implementada (pendiente de validación en Windows)
- «Mejorar en Gemini» copia la imagen (máx. 3072 px); modo app de escritorio (Alt+Espacio) o navegador
- La app vigila Descargas y adjunta el resultado sola; también Ctrl+V / «Pegar mejorada»
- Guía del Gem con «Copiar instrucciones» y carpeta de descargas configurable
- Estilo morado con iconos SVG, marca en la barra lateral e Inicio con favoritos en botones
- Checklist: `docs/acceptance/aceptacion.md` (sección Fase 2C)

## Fase 2D — implementada (pendiente de validación en Windows)
- Recorte manual estilo celular (libre o con proporción), con largo y precio en vivo
- Solo Gemini: sin mejora local automática ni Real-ESRGAN (código conservado y desactivado)
- Copia para Gemini en segundo plano (PNG/TIFF grandes); aviso si el resultado llega reducido
- Cuadro de precio sugerido en el panel; «Aprobar todo» acepta las mejoradas con Gemini

## Siguiente
- Fase 2: procesamiento por lotes en segundo plano con pool de procesos, pausa/reanudar/cancelar,
  persistencia en SQLite, historial y regeneración, registro de errores visible

## Fases siguientes
- Fase 3: ampliación local con IA
- Fase 4: Gemini
- Fase 5: instalador Windows
