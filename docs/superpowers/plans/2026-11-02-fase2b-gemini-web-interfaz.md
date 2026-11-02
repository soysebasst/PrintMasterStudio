# Fase 2B — Gemini web, interfaz rediseñada y acceso directo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mejorar imágenes con Gemini web (copiar el prompt, abrir la web, soltar el resultado), rediseñar la pantalla "Nuevo trabajo" según la maqueta aprobada y abrir la app con doble clic desde un acceso directo.

**Architecture:** La lógica nueva (adjuntar una mejora externa, calcular el "Siguiente:", el prompt y el lanzador web) vive en módulos Qt-free con sus pruebas. La UI se reorganiza sin cambiar el `JobController`, salvo por `attach_external`.

**Tech Stack:** sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-02-fase2b-gemini-web-interfaz-design.md`

## Global Constraints

- Gemini nunca se llama automáticamente. Esta fase no hace ninguna llamada de red a Gemini.
- Prompt por defecto: exactamente el de la §1 de la especificación. URL: `https://gemini.google.com/app?hl=es`.
- Tolerancia de proporción: 3 %. Objetivo del paso local: `settings.enhance_target_ppi` (150).
- El largo y el precio siempre salen de la proporción del original.
- Etiquetas de motor: `"Gemini (web)"` y `"Gemini (web) + Real-ESRGAN"` / `"Gemini (web) + Mejora básica"`.
- La cola en tarjetas usa `IconMode`. No hay botones ▲ ▼ Quitar grandes; esas acciones van en el menú contextual y con la tecla Supr.
- Cada vista tiene un solo botón primario: "Exportar N PDF".
- Acceso directo: `[project.gui-scripts] printmaster-studio = "printmaster.app:main"` (genera `.venv\Scripts\printmaster-studio.exe`, sin consola). `crear_acceso_directo.bat` crea accesos en el Escritorio y en el menú Inicio con el icono `src/printmaster/ui/assets/printmaster.ico`.

## Review Focus

1. **Soltar en la zona de mejora un archivo que no es imagen, o una imagen corrupta:** muestra un mensaje y conserva la mejora anterior. → Tarea 2.
2. **Gemini devuelve otra proporción (por ejemplo, cuadrada):** la lámina y el precio no cambian, la imagen no se deforma y aparece un aviso. → Tarea 2.
3. **El usuario abre la carpeta y el archivo descargado sigue siendo el mismo:** la app copia, nunca mueve ni modifica el archivo. → Tarea 2.
4. **Cola vacía o ítem en error:** "Siguiente:" muestra un texto útil y no se cae. → Tarea 3.
5. **Pantalla de 1366×768:** el panel derecho cabe sin desplazamiento con las Opciones avanzadas plegadas. → Tarea 6.

---

### Task 1: Acceso directo e icono
- Archivos: `pyproject.toml` (gui-scripts y package data `*.ico`/`*.png`), `src/printmaster/ui/assets/printmaster.ico` y `.png` (generados con Pillow por `tools/make_icon.py`), `crear_acceso_directo.bat`, `tools/crear_acceso_directo.ps1`, y `app.py` (`app.setWindowIcon`).
- [ ] Prueba `tests/unit/test_launcher.py`:
  - la gui-script `printmaster-studio` existe en `pyproject`;
  - el `.ico` abre con Pillow y contiene un tamaño de 256;
  - el `.ps1` contiene `printmaster-studio.exe`, `Desktop` y `Programs`.
- [ ] Ejecutar → FAIL. Implementar → PASS. Commit.

### Task 2: Adjuntar una mejora externa (Gemini web) en el controlador
- Archivos: `src/printmaster/core/enhance/gemini_web.py`, `src/printmaster/core/enhance/gemini_api.py` (solo la interfaz), `src/printmaster/app_services/job_controller.py`, `src/printmaster/infra/settings.py` (agregar `gemini_prompt: str = DEFAULT_PROMPT` y `advanced_open: bool = False`).
- En `gemini_web.py`:
  - `GEMINI_URL`, `DEFAULT_PROMPT`;
  - `ENGINE_GEMINI = "Gemini (web)"`;
  - `aspect_mismatch(a: tuple[int,int], b: tuple[int,int], tol=0.03) -> bool`;
  - `reveal_command(path: Path) -> list[str]`: `["explorer", f"/select,{path}"]` en Windows; `["xdg-open", str(path.parent)]` en otros sistemas.
- `JobController.attach_external(i: int, path: Path, enhancer: Enhancer | None = None) -> AttachResult`, con `AttachResult(result: EnhanceResult, aspect_warning: bool)`:
  1. `probe(path)`; si lanza `ImageLoadError`, se propaga sin cambiar nada.
  2. Copia como PNG a `data_dir()/cache/external/<sha_orig>_<sha_new>.png`.
  3. Si el PPI efectivo de esa copia (con la página del original) es menor que el objetivo y hay `enhancer`, llama a `enhancer.enhance(copia, sha_new, passes_needed(...), choose_model(...))` y combina la etiqueta.
  4. Guarda `enhanced` y `enhanced_info`, `enhanced_diagnosis = rerate(original_diagnosis, ppi)` y fija `enhance_choice = ON` si estaba en OFF. Luego hace `_revoke_approvals` por identidad.
- [ ] Pruebas `tests/integration/test_attach_external.py`:
  - un PNG de 2304×4096 para un original de 236×420 → página (600, 1100), precio 17000, `source_info.width_px == 2304`, motor `"Gemini (web)"`, PDF de 600×1100 mm; el original y el archivo soltado conservan su SHA.
  - Con un PNG de 236×420 (bajo PPI) y el `Enhancer` falso → la etiqueta contiene "+ Real-ESRGAN" y el ancho final es ≥ 900.
  - Con 1024×1024 → `aspect_warning is True`, la página sigue en (600, 1100) y la proporción del `dest_rect` es 1:1 (±0.01).
  - Con un `.jpg` corrupto → `ImageLoadError` y la mejora previa no cambia.
  - `aspect_mismatch((236,420),(2304,4096)) is False`.
- [ ] FAIL → implementar → PASS. Commit.

### Task 3: Texto "Siguiente:" y conteo exportable
- Archivo: `src/printmaster/app_services/next_step.py`, con `next_step(ctrl: JobController, analyzing: bool, enhancing: bool) -> str` y los textos exactos de la §2 de la especificación (el nombre va entre «»).
- [ ] Pruebas `tests/integration/test_next_step.py`: un caso por cada texto, incluidos la cola vacía y un ítem en error con otro aprobado.
- [ ] FAIL → implementar → PASS. Commit.

### Task 4: Cola en tarjetas
- Archivos: `src/printmaster/ui/widgets/queue_view.py` (reescrito: `CardDelegate`, `IconMode`, menú contextual, botón "+ Agregar" con menú, zona vacía) y `queue_model.py`:
  - `StatusTextRole` con la prioridad de la especificación;
  - `SizePriceRole`, que devuelve "60×110 · $17.000";
  - `OriginRole`: "IA" | "Gemini" | "Básica" | None.
- `QueueView` conserva `list`, `dropEvent`, `remove_selected()`, `current_changed`, `paths_added`, `add_paths`, `current_row()`, y agrega `move_up()` / `move_down()`. Las acciones del menú son `remove_action`, `up_action`, `down_action` y `reveal_action`.
- [ ] Ajustar `tests/ui/test_queue.py`: `up_btn`/`down_btn` pasan a `move_up()`/`move_down()`. Pruebas nuevas:
  - `StatusTextRole` devuelve "Mejorar" para baja calidad sin mejora, "Aprobada" tras aprobar y "Error" para un archivo corrupto;
  - `SizePriceRole` contiene "$";
  - el menú contextual tiene exactamente las acciones Quitar, Subir, Bajar y Abrir carpeta.
- [ ] FAIL → implementar → PASS. Commit.

### Task 5: Panel derecho (Tamaño, Ajuste, Calidad y Avanzadas)
- Archivos: `src/printmaster/ui/widgets/inspector.py` (reorganizado; conserva los nombres de los controles que usan las pruebas: `width_spin`, `height_spin`, `unit_combo`, `orientation_combo`, `favorites_combo`, `ppi_combo`, `ppi_spin`, `mode_combo` como modelo interno oculto, `background_combo`, `lossless_check`, `enhance_combo`, `issues_label` y `save_favorite_btn`).
  - Agrega `mode_buttons: dict[FitMode, QPushButton]`, que son checkables, exclusivos y sincronizados con `mode_combo`.
  - Agrega `advanced_box` (plegable, con `advanced_toggle`), que contiene la orientación, el PPI, "sin pérdida" y guardar formato.
  - Agrega `price_label`.
- `src/printmaster/ui/widgets/quality_panel.py` (nuevo): `QualityPanel`, con `level_chip`, `recommendation_label`, `gemini_btn`, `drop_zone` (`DropZone`, que acepta un archivo y emite `file_dropped(Path)`; con un clic abre `QFileDialog`), `status_label`, `details_toggle`, `details` (la `DiagnosisCard` existente adentro) y la nota de advertencia.
  - API: `show_item(diag, info, *, price, page_mm, enhanced, enhancing, error, downsample_ppi)` y `text()`, que concatena el texto visible y el de los detalles, para mantener compatibles las pruebas que usan `page.diagnosis.text()`.
- [ ] Pruebas `tests/ui/test_panel_2b.py`:
  - clic en `mode_buttons[FitMode.COVER]` → `inspector.mode() == FitMode.COVER`;
  - las Avanzadas están plegadas por defecto y su estado se guarda en `settings.advanced_open`;
  - `DropZone` emite `file_dropped` al simular un drop;
  - el chip muestra "Muy baja · 10 PPI";
  - `sizeHint().height()` del panel derecho con las Avanzadas plegadas es ≤ 700.
  - Ajustar las pruebas existentes del inspector si cambian textos.
- [ ] FAIL → implementar → PASS. Commit.

### Task 6: Página de trabajo, tema, Configuración y flujo Gemini
- Archivos: `job_page.py` (encabezado con chips de pasos, conmutador `original_btn`/`enhanced_btn` en lugar de `before_after_btn`, `info_label` bajo la vista previa, barra inferior con `next_label`, `total_label`, `progress` oculto salvo durante procesos, `cancel_enhance_btn`, `approve_all_btn`, `approve_btn` (ahora en el panel Calidad como "Aprobar esta") y `export_btn` con el texto "Exportar N PDF"), `theme.qss` (reescrito), `main_window.py` (iconos en la barra lateral), `settings_page.py` (secciones, `gemini_prompt_edit`, nota de la API) y `__main__`/`app.py` (icono).
- El flujo Gemini en `JobPage`:
  - `_on_gemini()`: copia `settings.gemini_prompt` con `QGuiApplication.clipboard()`, llama a `QDesktopServices.openUrl(GEMINI_URL)` y a `subprocess.Popen(reveal_command(path))`, y muestra un aviso en `next_label`;
  - `_on_external_dropped(path)`: `run_async(controller.attach_external, i, path, self.enhancer)` → refresca; si `aspect_warning`, muestra `_info` con el texto de la especificación; si falla, muestra `_info` con el error.
- [ ] Pruebas `tests/ui/test_job_page_2b.py` (con `QDesktopServices.openUrl` y `subprocess.Popen` sustituidos):
  - `gemini_btn` copia el prompt exacto, abre la URL y revela el archivo;
  - soltar un PNG de 2304×4096 → `"Gemini" in page.diagnosis.text()` y `total_label` con "$17.000";
  - `export_btn.text() == "Exportar 1 PDF"` tras aprobar;
  - `next_label` cambia según el estado;
  - el conmutador Original/Mejorada cambia la fuente de la vista previa.
  - Ajustar `test_job_page*.py` a los nombres nuevos.
  - `test_no_dead_buttons` en verde.
- [ ] FAIL → implementar → PASS. Commit.

### Task 7: Verificación y entrega
- [ ] Capturas offscreen a 1366×768 y 1440×860, en estados: vacío, con imágenes, mejorando, mejorada con Gemini y aprobadas. Revisarlas y corregir lo que se vea mal.
- [ ] README (acceso directo), aceptación (sección 2B) y PROGRESS.
- [ ] CI verde en Windows y Linux, revisión final independiente, corrección de hallazgos y merge a `main`.
