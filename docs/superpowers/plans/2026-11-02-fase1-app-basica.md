# PrintMaster Studio — Fase 1: Aplicación funcional básica — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una app de escritorio (PySide6) que carga imágenes en lote, las diagnostica, las ajusta a cualquier tamaño físico con tres modos (Ajustar / Rellenar / Recortar), muestra la vista previa exacta y exporta **un PDF por imagen** con dimensiones físicas exactas.

**Architecture:** El núcleo es Python puro, sin Qt (`domain/`, `core/`, `printers/`, `infra/`, `app_services/`), y tiene su propia batería de pruebas pytest. `layout.plan()` es una función pura que devuelve un `RenderPlan`; la vista previa y el PDF dibujan ese mismo plan. La UI (`ui/`) solo consume `JobController` y ejecuta el trabajo pesado en `QThreadPool`.

**Tech Stack:** Python ≥3.12, PySide6, Pillow, NumPy, opencv-python-headless, pikepdf (escritura de PDF), pydantic v2, pytest + pytest-qt + hypothesis + pypdf.

**Spec:** `docs/superpowers/specs/2026-11-02-printmaster-studio-design.md`

**Desviación de la especificación (decidida en este plan):** el PDF se escribe con **pikepdf (MPL-2.0)** en lugar de ReportLab. ReportLab no incrusta perfiles ICC en las imágenes de forma directa, y la especificación exige "evitar cambios inesperados de color" (§11) además de la inserción byte a byte del JPEG. Con pikepdf se construye el objeto de imagen a mano: `DCTDecode` con los bytes originales, `ICCBased`, `SMask` para la transparencia y `ViewerPreferences/PrintScaling /None`. Este cambio reemplaza la tarea "spike de PDF" del §10.2 de la especificación.

## Global Constraints

- Python `>=3.12`, Windows 10/11 x64 como destino; también debe correr en Linux para CI. Paquete `src/printmaster`, se ejecuta con `python -m printmaster`.
- Prohibidas las dependencias AGPL (PyMuPDF, Upscayl). Solo se permiten licencias permisivas, LGPL o MPL.
- Las unidades físicas se manejan internamente en **mm como `Decimal`**. `pt = mm × 72 / 25.4`. `px = round_half_up(mm / 25.4 × ppi)`.
- PPI de la imagen ≠ DPI de la impresora: los 2400×1200 dpi **nunca** entran en ningún cálculo.
- PPI configurables: 100, 150, 200, 250, 300 o personalizado (rango válido 50–600). El valor por defecto es 200.
- Clasificación por defecto: Excelente ≥250 · Buena 180–249 · Aceptable 120–179 · Baja 72–119 · Muy baja <72 PPI.
- Epson SC-T3170: rollo de 329–610 mm de ancho, hoja de 210–610 mm, margen lateral de 3 mm por lado, largo máximo de página 5080 mm (límite del PDF).
- El archivo original **nunca** se modifica, mueve ni borra.
- La imagen no se interpola hacia arriba: si `effective_ppi` es menor que el PPI elegido, se incrusta tal cual. Si es mayor que `ppi × 1.01`, se reduce a `ppi` con Lanczos.
- PDF: una página por archivo, `MediaBox = [0 0 W H]` en pt exactos, sin márgenes añadidos y con `/ViewerPreferences << /PrintScaling /None >>`. Un archivo por imagen.
- La salida raster va sin pérdida (Flate) por defecto. Solo se re-codifica en JPEG (calidad 95, 4:4:4) si `lossless=False` **y** la fuente era JPEG.
- Toda la interfaz está en español. Ningún botón visible queda sin función: las secciones de fases futuras (Historial, IA) **no** aparecen en la barra lateral en la Fase 1.
- Toda escritura de archivo es atómica: se escribe un `.tmp` en la misma carpeta y luego se hace `os.replace`.
- Commits con el pie `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Fotos de celular con orientación EXIF 6/8**: la página automática y la vista previa deben usar las dimensiones ya rotadas, y el paso directo se desactiva para que el PDF no salga girado. → pruebas en las Tareas 4, 5 y 7.
2. **Rutas con tildes, ñ y espacios** (fuente y carpeta de salida, p. ej. `Diseños/Señal Peña.jpg`): se cargan y exportan sin errores. → pruebas en las Tareas 4 y 7.
3. **JPEG en CMYK** enviados por diseñadores: se convierten a RGB, nunca pasan en directo y los colores no salen invertidos. → pruebas en las Tareas 4 y 7.
4. **Reexportar con el mismo nombre**: nunca se sobrescribe (se agrega el sufijo `_2`) y no queda un PDF a medio escribir si algo falla. → pruebas en las Tareas 7 y 8.
5. **PNG con transparencia** (logos): se aplana sobre blanco por defecto, sin fondo negro; con `keep_alpha=True` se incluye una `SMask`. → pruebas en las Tareas 6 y 7.

---

## Mapa de archivos

```
pyproject.toml · README.md · PROGRESS.md · .gitignore · .github/workflows/ci.yml
src/printmaster/__init__.py · __main__.py · app.py
src/printmaster/domain/{__init__,units,models,quality}.py
src/printmaster/printers/{__init__,profiles}.py · epson_sc_t3170.json
src/printmaster/core/{__init__,image_loader,layout,color,composer,pdf_writer,naming,image_analyzer}.py
src/printmaster/infra/{__init__,paths,settings,logging_setup}.py
src/printmaster/app_services/{__init__,job_controller}.py
src/printmaster/ui/{__init__,theme,theme.qss,workers,main_window}.py
src/printmaster/ui/models/queue_model.py
src/printmaster/ui/widgets/{queue_view,preview_canvas,inspector,diagnosis_card}.py
src/printmaster/ui/pages/{home_page,job_page,settings_page}.py
tests/conftest.py · tests/unit/… · tests/integration/… · tests/ui/…
docs/acceptance/fase1-checklist.md
```

`tests/conftest.py` contiene una factoría de imágenes sintéticas: `make_image(tmp_path, name, size=(w,h), mode="RGB", fmt="JPEG", exif_orientation=None, icc=None, pattern="texture")`. Escribe en `tmp_path` y devuelve un `Path`. `pattern="texture"` genera ruido de valor suavizado, con detalle y reproducible (semilla fija). Todas las pruebas que necesitan imágenes usan esta factoría.

---

### Task 1: Esqueleto del proyecto y CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `PROGRESS.md`, `.github/workflows/ci.yml`, `src/printmaster/__init__.py`, `tests/conftest.py`, `tests/unit/test_smoke.py`

**Interfaces:**
- Produces: `printmaster.__version__ = "0.1.0"`; la fixture `make_image` descrita arriba.

- [ ] **Step 1:** Crear `pyproject.toml` (build hatchling, `requires-python = ">=3.12"`).
  - Dependencias: `PySide6>=6.7`, `Pillow>=10.3`, `numpy>=1.26`, `opencv-python-headless>=4.9`, `pikepdf>=9.0`, `pydantic>=2.7`.
  - Extra `dev`: `pytest>=8`, `pytest-qt>=4.4`, `hypothesis>=6.100`, `pypdf>=4.2`, `ruff>=0.5`, `psutil>=5.9`.
  - `[tool.pytest.ini_options] testpaths=["tests"]`, `qt_api="pyside6"`, markers `ui`.
  - `[tool.ruff] line-length=100`.
- [ ] **Step 2:** Escribir `tests/unit/test_smoke.py::test_version` (`assert printmaster.__version__ == "0.1.0"`) y `test_make_image_creates_readable_jpeg` (que la factoría produzca un JPEG de 40×30 que Pillow abre con `size == (40, 30)`).
- [ ] **Step 3:** `pip install -e .[dev]` y luego `pytest -q`. Esperado: 2 passed.
- [ ] **Step 4:** Crear `ci.yml` con una matriz `ubuntu-latest` y `windows-latest`, Python 3.12, `pip install -e .[dev]`, `ruff check .` y `pytest -q`, con `QT_QPA_PLATFORM=offscreen` en el env. En Ubuntu, instalar antes con apt `libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3 libfontconfig1`.
- [ ] **Step 5:** Crear `PROGRESS.md` con las secciones "Hecho", "En curso" y "Pendiente" (copiar las tareas 1–17 de este plan como pendientes) y un `README.md` mínimo con los comandos para instalar, ejecutar y probar.
- [ ] **Step 6:** Commit `chore: esqueleto del proyecto, pruebas y CI`.

### Task 2: Dominio — unidades, modelos y calidad

**Files:**
- Create: `src/printmaster/domain/units.py`, `models.py`, `quality.py`
- Test: `tests/unit/test_units.py`, `test_models.py`, `test_quality.py`

**Interfaces:**
- Produces (`units`):
  - `class Unit(StrEnum): MM="mm"; CM="cm"; IN="in"`
  - `to_mm(value: Decimal | int | float | str, unit: Unit) -> Decimal` (convertir con `Decimal(str(value))`)
  - `from_mm(mm: Decimal, unit: Unit) -> Decimal`
  - `mm_to_pt(mm: Decimal) -> float`
  - `mm_to_px(mm: Decimal, ppi: int) -> int` (ROUND_HALF_UP)
  - `effective_ppi(px: int, mm: Decimal) -> float`
- Produces (`models`, todos `@dataclass(frozen=True)`):
  - `Orientation(StrEnum)`: `AUTO, PORTRAIT, LANDSCAPE`
  - `FitMode(StrEnum)`: `CONTAIN="ajustar", FILL="rellenar", COVER="recortar"`
  - `BackgroundKind(StrEnum)`: `WHITE, COLOR, EDGE_COLOR, BLUR`
  - `Background(kind: BackgroundKind = WHITE, color: tuple[int,int,int] = (255,255,255))`
  - `CropOffset(x: float = 0.5, y: float = 0.5)`: cada valor se recorta a [0,1] en `__post_init__`; 0 = izquierda/arriba.
  - `PrintSpec(width_mm: Decimal, height_mm: Decimal, ppi: int = 200, orientation: Orientation = AUTO)`, con el método `resolved_for(img_w: int, img_h: int) -> PrintSpec`, que devuelve dimensiones ya orientadas y `orientation` ≠ AUTO. En AUTO, la página se orienta igual que la imagen (si la imagen es cuadrada, se deja como está). PORTRAIT obliga alto ≥ ancho; LANDSCAPE, ancho ≥ alto.
  - `ImageInfo(path: Path, format: str, width_px: int, height_px: int, mode: str, has_alpha: bool, icc: bytes | None, exif_orientation: int, file_size: int, sha256: str)`. `width_px/height_px` son las dimensiones **después** de aplicar EXIF.
  - `RenderPlan(page_w_mm: Decimal, page_h_mm: Decimal, page_w_pt: float, page_h_pt: float, src_box: tuple[int,int,int,int], dest_rect_pt: tuple[float,float,float,float], output_px: tuple[int,int] | None, compose_page: bool, background: Background, effective_ppi: float, passthrough: bool)`. `src_box` es (l,t,r,b) en píxeles de la imagen ya rotada. `dest_rect_pt` es (x,y,w,h) con origen PDF abajo a la izquierda.
  - `ItemStatus(StrEnum)`: `PENDING, ANALYZED, READY, APPROVED, EXPORTED, ERROR`
- Produces (`quality`):
  - `QualityLevel(Enum)` con los valores `EXCELENTE="Excelente"`, `BUENA="Buena"`, `ACEPTABLE="Aceptable"`, `BAJA="Baja resolución"`, `MUY_BAJA="Muy baja resolución"`
  - `QualityThresholds(excelente=250, buena=180, aceptable=120, baja=72)` (frozen)
  - `classify(ppi: float, t: QualityThresholds = DEFAULT_THRESHOLDS) -> QualityLevel`
  - `downgrade(level) -> QualityLevel` (MUY_BAJA se queda en MUY_BAJA)

- [ ] **Step 1: Pruebas.**
  - `to_mm(60, CM) == Decimal("600")`, `to_mm(24, IN) == Decimal("609.6")`.
  - Propiedad con hypothesis: `from_mm(to_mm(v,u),u) == Decimal(str(v))` para v entre 0.1 y 10000 con 2 decimales.
  - `abs(mm_to_pt(Decimal(600)) - 1700.7874) < 0.001`.
  - `mm_to_px(Decimal(600), 200) == 4724`, `mm_to_px(Decimal(900), 200) == 7087`.
  - `effective_ppi(4724, Decimal(600)) ≈ 199.99` (±0.05).
  - `PrintSpec(600,900).resolved_for(4000,3000)` da ancho 900 y alto 600; con `PORTRAIT` y la misma imagen da ancho 600 y alto 900.
  - `CropOffset(1.5,-2) == CropOffset(1.0,0.0)`.
  - `classify` en los límites: 250→EXCELENTE, 249.9→BUENA, 180→BUENA, 179.9→ACEPTABLE, 120→ACEPTABLE, 72→BAJA, 71.9→MUY_BAJA. `downgrade(BUENA) == ACEPTABLE`.
- [ ] **Step 2:** `pytest tests/unit/test_units.py tests/unit/test_models.py tests/unit/test_quality.py -q` → FAIL (ImportError).
- [ ] **Step 3:** Implementar los tres módulos.
- [ ] **Step 4:** Mismo comando → PASS.
- [ ] **Step 5:** Commit `feat(domain): unidades, modelos y clasificación de calidad`.

### Task 3: Perfil de impresora y validación

**Files:**
- Create: `src/printmaster/printers/profiles.py`, `src/printmaster/printers/epson_sc_t3170.json`
- Test: `tests/unit/test_profiles.py`

**Interfaces:**
- Consumes: `PrintSpec` (T2).
- Produces:
  - `PrinterProfile(id, name, roll_min_mm: Decimal, roll_max_mm: Decimal, sheet_min_mm: Decimal, sheet_max_mm: Decimal, side_margin_mm: Decimal, max_length_mm: Decimal)` (frozen)
  - `ValidationIssue(level: Literal["error","warning"], code: str, message: str)`
  - `load_profile(profile_id: str = "epson_sc_t3170") -> PrinterProfile` (con `importlib.resources`)
  - `list_profiles() -> list[PrinterProfile]` (todos los `*.json` de la carpeta; así se pueden agregar impresoras en el futuro)
  - `validate(spec: PrintSpec, profile: PrinterProfile) -> list[ValidationIssue]`. El *ancho* de la página resuelta es lo que cruza el rollo.
- JSON: `{"id":"epson_sc_t3170","name":"Epson SureColor SC-T3170","roll_min_mm":329,"roll_max_mm":610,"sheet_min_mm":210,"sheet_max_mm":610,"side_margin_mm":3,"max_length_mm":5080}`

Reglas de `validate`, con códigos y mensajes exactos en español:

| Condición | level | code | message |
|---|---|---|---|
| ancho o alto ≤ 0 | error | `invalid` | "Las dimensiones deben ser mayores que cero." |
| ancho > roll_max y alto > roll_max | error | `too_wide` | "Ningún lado cabe en la impresora (máx. 610 mm de ancho)." |
| ancho > roll_max y alto ≤ roll_max | warning | `rotate` | "El ancho supera 610 mm; gire el formato para imprimir." |
| alto > max_length_mm | error | `too_long` | "El largo supera 5080 mm, el máximo de un PDF." |
| roll_max − 2·margin < ancho ≤ roll_max | warning | `margin` | "El diseño invade los márgenes físicos de 3 mm del rollo." |

- [ ] **Step 1: Pruebas.** `load_profile().roll_max_mm == 610`. 600×900 → `[]`. 606×900 → [`margin`]. 900×600 → [`rotate`]. 700×700 → [`too_wide`]. 600×6000 → [`too_long`]. 0×900 → [`invalid`]. `list_profiles()` contiene el id `epson_sc_t3170`.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar. Incluir el JSON como *package data* (`[tool.hatch.build] include`).
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(printers): perfil Epson SC-T3170 y validación de formato`.

### Task 4: Carga de imágenes

**Files:**
- Create: `src/printmaster/core/image_loader.py`
- Test: `tests/unit/test_image_loader.py`

**Interfaces:**
- Consumes: `ImageInfo` (T2).
- Produces:
  - `SUPPORTED_EXTENSIONS = frozenset({".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff"})`
  - `class ImageLoadError(Exception)` con un mensaje en español que incluye el nombre del archivo
  - `collect_images(paths: Iterable[Path]) -> list[Path]`: expande carpetas de forma recursiva, filtra por extensión sin distinguir mayúsculas, elimina rutas repetidas y ordena de forma natural (`img2` antes que `img10`).
  - `probe(path: Path) -> ImageInfo`: sin decodificar los píxeles; el SHA-256 se calcula por bloques de 1 MiB.
  - `load_rgb(path: Path) -> tuple[Image.Image, bytes | None]`: aplica EXIF; toma el primer cuadro; convierte 16 bits/`I;16`/`I`/`F` a 8 bits; pasa CMYK a RGB con `ImageCms` si hay ICC (si no, con `convert("RGB")`) y en ese caso devuelve el ICC de **sRGB**; pasa `P`/`LA` a `RGBA` o `RGB` según haya transparencia. Devuelve siempre un modo de `{"RGB","RGBA","L"}` y el ICC correspondiente.
  - `load_proxy(path: Path, max_side: int = 2048) -> Image.Image` (RGB, usando `draft()` en JPEG)
  - `make_thumbnail(path: Path, max_side: int = 256) -> Image.Image`
  - Al importar el módulo: `Image.MAX_IMAGE_PIXELS = 400_000_000`. Un archivo corrupto, inexistente o más grande que eso genera `ImageLoadError`.

- [ ] **Step 1: Pruebas.**
  - `probe` de un JPEG de 400×300 con EXIF orientación 6 → `width_px==300, height_px==400, exif_orientation==6`.
  - `load_rgb` del mismo archivo → `size==(300,400)`.
  - Un archivo en `tmp_path/"Diseños"/"Señal Peña ó.jpg"` → `probe` y `load_rgb` funcionan.
  - JPEG CMYK (crear con Pillow en modo CMYK, color de relleno (0,255,255,0), es decir magenta) → `load_rgb` devuelve `mode=="RGB"`, con el píxel central de R alto, G bajo y B alto (no invertido).
  - TIFF de 16 bits (`I;16`) → `mode in {"L","RGB"}`.
  - PNG RGBA → `mode=="RGBA"` y `has_alpha is True`.
  - Archivo con bytes basura y extensión `.jpg` → `pytest.raises(ImageLoadError)`.
  - `collect_images([carpeta])` con `a10.png, a2.JPG, notas.txt` dentro de una subcarpeta → `[a2.JPG, a10.png]`.
  - `make_thumbnail(...)`: el lado mayor del resultado mide ≤ 256.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(core): carga segura de imágenes`.

### Task 5: Motor de ajuste (`layout.plan`)

**Files:**
- Create: `src/printmaster/core/layout.py`
- Test: `tests/unit/test_layout.py`

**Interfaces:**
- Consumes: `PrintSpec, FitMode, Background, CropOffset, RenderPlan, ImageInfo` (T2) y `units` (T2).
- Produces:
  - `plan(info: ImageInfo, spec: PrintSpec, mode: FitMode, background: Background = Background(), crop: CropOffset = CropOffset()) -> RenderPlan`
  - `full_image_rect_pt(plan: RenderPlan, img_w: int, img_h: int) -> tuple[float,float,float,float]`: el rectángulo donde caería la imagen **completa** con la escala del plan. Se usa para el paso directo en modo Recortar: la imagen se sale de la página y el MediaBox la recorta.

Algoritmo:
1. `s = spec.resolved_for(info.width_px, info.height_px)`.
2. CONTAIN/FILL: `src_box = (0,0,W,H)`. La escala es la menor entre `page_w/W` y `page_h/H`. `dest_rect` queda centrado.
3. COVER: `dest_rect = página completa`. `src_box` es el rectángulo más grande con la proporción de la página dentro de la imagen, desplazado según `crop.x/crop.y` sobre el sobrante (con enteros redondeados).
4. `effective_ppi = min(src_w / dest_w_in, src_h / dest_h_in)`.
5. Si `effective_ppi > s.ppi × 1.01`, entonces `output_px = (mm_to_px(dest_w_mm, ppi), mm_to_px(dest_h_mm, ppi))`; si no, `None`.
6. `compose_page = (mode == FILL and background.kind == BLUR)`. En ese caso `output_px` = la página completa al PPI `min(s.ppi, effective_ppi)` y `dest_rect` = página completa.
7. En CONTAIN el fondo se fuerza a `Background()` (blanco). `EDGE_COLOR` llega ya resuelto a `COLOR` (lo hace T11); si `plan` lo recibe sin resolver, genera `ValueError`.
8. `passthrough = info.format == "JPEG" and info.mode in {"RGB","L"} and info.exif_orientation in {0,1} and output_px is None and not compose_page`.

- [ ] **Step 1: Pruebas.**
  - 4000×3000 JPEG en 600×900 mm AUTO + CONTAIN → página 900×600 mm (horizontal). Como 4:3 ≠ 3:2, quedan bandas a los lados: `dest_h == page_h_pt`, `dest_w/dest_h ≈ 4/3` (±0.001) y el rectángulo está centrado en horizontal.
  - El mismo caso con COVER → `dest_rect` = página, `src_box` con proporción 3:2 (±1 px). Con `crop=CropOffset(0,0)` tiene `top==0`; con `CropOffset(1,1)` tiene `bottom==3000`.
  - Imagen de 1000 px de ancho en 600 mm → `effective_ppi ≈ 42.3`, `output_px is None`, `passthrough is True`.
  - Imagen de 12000×8000 en 600×400 mm a 200 PPI → `output_px == (4724, 3150)` (±1) y `passthrough is False`.
  - EXIF 6 → `passthrough is False`.
  - FILL + BLUR → `compose_page is True` y `dest_rect` = página.
  - Propiedad con hypothesis (W,H entre 1 y 20000; ancho y alto entre 10 y 3000 mm; los tres modos): en CONTAIN el `dest_rect` queda dentro de la página (±1e-6); en COVER el `src_box` queda dentro de la imagen; la proporción se conserva (±1 px en `src_box`).
  - `full_image_rect_pt` en COVER contiene al `dest_rect`.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(core): planificación de ajuste contain/fill/cover`.

### Task 6: Color y composición raster

**Files:**
- Create: `src/printmaster/core/color.py`, `src/printmaster/core/composer.py`
- Test: `tests/unit/test_color.py`, `tests/unit/test_composer.py`

**Interfaces:**
- Consumes: `RenderPlan, Background` (T2) y `load_rgb` (T4).
- Produces:
  - `flatten_alpha(img: Image.Image, color=(255,255,255)) -> Image.Image` (RGBA→RGB; los demás modos sin cambios)
  - `edge_color(img: Image.Image, band: float = 0.02) -> tuple[int,int,int]` (mediana del borde)
  - `srgb_icc() -> bytes` (`ImageCms.createProfile("sRGB")` serializado; se guarda en caché)
  - `render_raster(img: Image.Image, plan: RenderPlan, keep_alpha: bool = False) -> Image.Image`: recorta `src_box`; si hay `output_px`, redimensiona con LANCZOS; aplana la transparencia salvo que `keep_alpha`. Si `compose_page`, el fondo es la propia imagen en modo cover a tamaño de página con `GaussianBlur(radius=max(4, 0.02·lado_mayor))`, y la imagen en modo contain se pega centrada encima.

- [ ] **Step 1: Pruebas.**
  - RGBA totalmente transparente → `flatten_alpha` da (255,255,255) en el centro; **no** (0,0,0).
  - `edge_color` de una imagen con borde rojo y centro azul → ≈ (255,0,0).
  - `render_raster` de una imagen de 1000×800 con `output_px=(500,400)` → `size == (500,400)`.
  - Con `compose_page` y página de 900×600 px para una imagen de 300×600 → `size == (900,600)` y la columna central igual a la imagen redimensionada (diferencia media < 3).
  - `keep_alpha=True` conserva RGBA.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(core): manejo de color y composición raster`.

### Task 7: Escritor de PDF (pikepdf)

**Files:**
- Create: `src/printmaster/core/pdf_writer.py`
- Test: `tests/integration/test_pdf_writer.py`

**Interfaces:**
- Consumes: `ImageInfo, RenderPlan` (T2), `load_rgb` (T4), `full_image_rect_pt` (T5), `render_raster, flatten_alpha, srgb_icc` (T6).
- Produces:
  - `@dataclass(frozen=True) ExportOptions(lossless: bool = True, jpeg_quality: int = 95, keep_alpha: bool = False)`
  - `class PdfExportError(Exception)`
  - `write_pdf(info: ImageInfo, plan: RenderPlan, out_path: Path, options: ExportOptions = ExportOptions()) -> Path`

Construcción del PDF:
1. `pikepdf.new()` y una página con `MediaBox [0 0 page_w_pt page_h_pt]`.
2. `Root.ViewerPreferences = << /PrintScaling /None >>`.
3. Metadatos `Info`: `/Title` (nombre del original), `/Creator "PrintMaster Studio 0.1.0"` y `/Subject "<ancho>×<alto> mm · <ppi> PPI efectivos"`.
4. Fondo: si `background.kind == COLOR`, un rectángulo lleno `r g b rg 0 0 W H re f` (vector, sin raster).
5. Imagen:
   - **Paso directo:** los bytes del archivo original en un stream con `/Filter /DCTDecode`. El rectángulo es `dest_rect` (CONTAIN/FILL) o `full_image_rect_pt` (COVER).
   - **Raster:** `render_raster`. Si `lossless` o la fuente no era JPEG, va como `/FlateDecode` de `tobytes()`. Si no, se re-codifica JPEG calidad 95 con `subsampling=0` y `/DCTDecode`.
   - `ColorSpace`: `[/ICCBased <stream /N 3|1>]` con el ICC de la imagen (o `srgb_icc()` si no tiene). Con `keep_alpha` y RGBA: `/SMask` con el canal alfa (Flate, DeviceGray).
6. Contenido: `q w 0 0 h x y cm /Im0 Do Q`.
7. Se guarda en `out_path.with_suffix(".pdf.tmp")` y luego `os.replace` a `out_path`. Ante cualquier excepción se borra el `.tmp` y se lanza `PdfExportError`. Crea las carpetas padre.

- [ ] **Step 1: Pruebas** (se leen con **pypdf**, independiente de pikepdf).
  - Formatos parametrizados (60×45, 60×90, 60×120, 50×70, 40×60, 60×150 en cm; 600×900 en mm; 24×36 en in) con CONTAIN y COVER → una sola página. `|MediaBox.width − mm·72/25.4| < 0.01` (igual para el alto), según la página **resuelta**. `/PrintScaling == /None`.
  - Paso directo: `reader.pages[0]["/Resources"]["/XObject"]["/Im0"].get_object()._data` (bytes codificados, sin decodificar) es **idéntico byte a byte** a `path.read_bytes()`.
  - Recorte con paso directo (COVER, imagen 4:3 en página 1:1) → el rectángulo de la imagen dentro del contenido (se lee la matriz `cm`) es más ancho que la página.
  - Fuente PNG → filtro `/FlateDecode` y píxeles decodificados iguales a `render_raster` (máximo de diferencia 0).
  - ICC presente: el ColorSpace es `ICCBased`.
  - PNG RGBA con `keep_alpha=False` → sin SMask y píxel central blanco. Con `keep_alpha=True` → hay `/SMask`.
  - JPEG CMYK → `passthrough False` y el ColorSpace tiene N=3.
  - Fuente JPEG con `lossless=False` y `output_px` definido → `/DCTDecode`.
  - Salida en `tmp_path/"Salida Peña"/"x.pdf"` → el archivo existe y no queda ningún `*.tmp`.
  - Si se fuerza un fallo (monkeypatch de `pikepdf.Pdf.save` para que lance un error) → `PdfExportError`, no queda `x.pdf` ni `.tmp`.
  - EXIF 6: el PDF tiene la imagen en vertical (la imagen decodificada tiene alto > ancho).
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(core): PDF individual con dimensiones físicas exactas`.

### Task 8: Nombres de salida

**Files:**
- Create: `src/printmaster/core/naming.py`
- Test: `tests/unit/test_naming.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) NamingOptions(prefix: str = "Cliente", start: int = 1, digits: int = 3, use_original_name: bool = False, by_date: bool = True, client: str = "")`
  - `sanitize(name: str) -> str`: elimina `<>:"/\|?*` y los caracteres de control, quita espacios y puntos al final, protege los nombres reservados de Windows (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`9`, `LPT1`–`9`, a los que agrega `_`) y deja `"sin_nombre"` si el resultado queda vacío.
  - `output_path(base_dir: Path, index: int, src: Path, opts: NamingOptions, today: date) -> Path`: devuelve `base/[AAAA-MM-DD/][cliente/]<prefijo>_<NNN>.pdf`, o `<stem original>.pdf` si `use_original_name`. El número es `start + index`.
  - `unique_path(p: Path) -> Path`: si `p` existe, prueba `_2`, `_3`, …

- [ ] **Step 1: Pruebas.**
  - `output_path(base, 0, Path("a.jpg"), NamingOptions(client="Peña"), date(2026,11,2)) == base/"2026-11-02"/"Peña"/"Cliente_001.pdf"`.
  - Con `index=41` → `Cliente_042.pdf`. Con `digits=4` → `Cliente_0001.pdf`.
  - `use_original_name=True` con `Path("foto final.png")` → `foto final.pdf`.
  - `sanitize('a:b*?.') == "ab"` y `sanitize("CON") == "CON_"`.
  - `unique_path` cuando ya existen `x.pdf` y `x_2.pdf` → `x_3.pdf`.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(core): nombres y carpetas de salida`.

### Task 9: Diagnóstico de imagen

**Files:**
- Create: `src/printmaster/core/image_analyzer.py`
- Test: `tests/unit/test_image_analyzer.py`

**Interfaces:**
- Consumes: `ImageInfo` (T2), `classify, downgrade, QualityLevel, QualityThresholds` (T2) y `load_proxy` (T4).
- Produces:
  - `@dataclass(frozen=True) Diagnosis(effective_ppi: float, base_level: QualityLevel, level: QualityLevel, sharpness: float, noise_sigma: float, blockiness: float, jpeg_quality: int | None, warnings: tuple[str, ...], recommendation: str)`
  - `measure_sharpness(gray: np.ndarray) -> float`: varianza del Laplaciano de OpenCV, calculada sobre el gris redimensionado a un lado mayor de 1024.
  - `estimate_noise(gray: np.ndarray) -> float`: método de Immerkær (1996), con kernel `[[1,-2,1],[-2,4,-2],[1,-2,1]]` y `sigma = sqrt(pi/2) · sum|conv| / (6·(W−2)·(H−2))`.
  - `measure_blockiness(gray: np.ndarray) -> float`: media de |diferencia horizontal| en columnas múltiplo de 8 dividida por la media en el resto (≈1.0 significa sin bloques).
  - `estimate_jpeg_quality(img: Image.Image) -> int | None`: compara `img.quantization[0]` con la tabla de luminancia estándar de libjpeg (escala IJG) y devuelve la calidad 1–100 más cercana. Si la imagen no es JPEG, `None`.
  - Constantes: `BLUR_THRESHOLD`, `NOISE_THRESHOLD = 8.0`, `BLOCK_THRESHOLD = 1.5`. `BLUR_THRESHOLD` se calibra con las pruebas.
  - `analyze(info: ImageInfo, proxy: Image.Image, effective_ppi: float, thresholds: QualityThresholds = DEFAULT_THRESHOLDS) -> Diagnosis`. Si se activa cualquiera de los tres detectores (desenfoque, ruido o bloques), `level = downgrade(base_level)` **una sola vez**.
  - Mensajes de advertencia exactos:
    - "Posible desenfoque."
    - "Ruido visible."
    - "Artefactos de compresión JPEG."
    - "Pocos píxeles para este tamaño: {ppi:.0f} PPI efectivos." (solo si el nivel base es BAJA o MUY_BAJA)
  - Recomendaciones exactas:
    - ≥ ACEPTABLE sin advertencias → "Conservar la imagen original."
    - BAJA o MUY_BAJA → "Se recomienda ampliar (Fase 3) o reducir el tamaño de impresión."
    - Otro caso → "Revisar la vista previa antes de aprobar."
  - Nunca se dice "alta calidad" basándose solo en la cantidad de píxeles.

- [ ] **Step 1: Pruebas.**
  - La nitidez baja de forma estricta en una textura con desenfoque gaussiano σ = 0, 1, 2, 4.
  - σ=4 activa "Posible desenfoque."; σ=0 no la activa.
  - Ruido gaussiano σ=10 sobre gris plano → `estimate_noise` entre 8 y 12.
  - JPEG calidad 20 → `blockiness > 1.5` y `estimate_jpeg_quality` entre 15 y 25. JPEG calidad 95 → resultado entre 90 y 100.
  - `analyze` con `effective_ppi=60` → nivel `MUY_BAJA` y el texto de advertencia correspondiente.
  - Con `effective_ppi=300` y una imagen nítida → `EXCELENTE` y "Conservar la imagen original."
  - Con `effective_ppi=300` y desenfoque σ=4 → `level == BUENA`.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar y calibrar `BLUR_THRESHOLD` entre los valores de σ=2 y σ=4 del fixture.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(core): diagnóstico de nitidez, ruido, compresión y PPI efectivo`.

### Task 10: Infraestructura — rutas, configuración y logs

**Files:**
- Create: `src/printmaster/infra/paths.py`, `settings.py`, `logging_setup.py`
- Test: `tests/unit/test_settings.py`, `tests/unit/test_logging.py`

**Interfaces:**
- Consumes: `Unit` (T2) y `NamingOptions` (T8).
- Produces:
  - `config_dir() -> Path`, `data_dir() -> Path`, `default_output_dir() -> Path`. Si existe la variable de entorno `PRINTMASTER_HOME`, se usa `$PRINTMASTER_HOME/config|data|output`. En Windows: `%APPDATA%\PrintMasterStudio`, `%LOCALAPPDATA%\PrintMasterStudio` y `~/Documents/PrintMaster`. En otros sistemas: `~/.printmaster/...`. Las carpetas se crean al consultarlas.
  - pydantic: `FavoriteFormat(name: str, width: Decimal, height: Decimal, unit: Unit)` y `Settings(output_dir: Path, default_ppi: int = 200 (rango 50–600), default_unit: Unit = CM, default_mode: FitMode = CONTAIN, printer_id: str = "epson_sc_t3170", naming_prefix: str = "Cliente", naming_digits: int = 3, naming_by_date: bool = True, favorites: list[FavoriteFormat])`.
  - Favoritos por defecto: `60×45, 60×90, 60×120, 50×70, 40×60, 60×150` en cm, con el nombre `"60 × 45 cm"`, etc.
  - `load_settings(path: Path | None = None) -> Settings` (por defecto `config_dir()/settings.json`). Si no existe, devuelve los valores por defecto. Si el JSON es inválido, lo renombra a `settings.json.bak` y devuelve los valores por defecto.
  - `save_settings(s: Settings, path: Path | None = None) -> None` (escritura atómica).
  - `setup_logging(log_dir: Path | None = None) -> logging.Logger`: `RotatingFileHandler("printmaster.log", 1 MB, 5 copias)` más un `RedactingFilter` que reemplaza `AIza[0-9A-Za-z_\-]{35}` y `(api[_-]?key\s*[=:]\s*)\S+` por `***`.

- [ ] **Step 1: Pruebas** (con `monkeypatch.setenv("PRINTMASTER_HOME", tmp_path)`).
  - Ida y vuelta: `save_settings` y luego `load_settings` devuelve un objeto igual.
  - Por defecto hay 6 favoritos.
  - Un JSON corrupto produce `.bak` y valores por defecto.
  - `default_ppi=1000` genera `ValidationError`.
  - Registrar `"api_key=AIza" + "x"*35` en el log → el archivo contiene `***` y no contiene `AIza`.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(infra): rutas, configuración y logs con ocultamiento de claves`.

### Task 11: `JobController` (servicio de aplicación, sin Qt)

**Files:**
- Create: `src/printmaster/app_services/job_controller.py`
- Test: `tests/integration/test_job_controller.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces:
  - `@dataclass JobItem(path: Path, info: ImageInfo | None = None, status: ItemStatus = PENDING, diagnosis: Diagnosis | None = None, crop: CropOffset = CropOffset(), duplicate_of: int | None = None, error: str | None = None, output: Path | None = None)`
  - `@dataclass ExportResult(index: int, ok: bool, output: Path | None, error: str | None)`
  - `class JobController`, con `__init__(self, settings: Settings, profile: PrinterProfile)` y los atributos públicos `items: list[JobItem]`, `spec: PrintSpec`, `mode: FitMode`, `background: Background`, `export_options: ExportOptions`, `naming: NamingOptions`.
  - Métodos:
    - `add_paths(paths: Iterable[Path]) -> list[int]`: usa `collect_images` y `probe`. Un error deja el ítem en ERROR con su mensaje. Marca `duplicate_of` cuando el SHA-256 coincide. Devuelve los índices nuevos.
    - `remove(indices: Iterable[int]) -> None`
    - `move(src: int, dst: int) -> None`
    - `set_spec(spec)`, `set_mode(mode)`, `set_background(bg)` y `set_crop(i, crop)`. Cada cambio devuelve al estado READY los ítems que ya estaban APPROVED.
    - `issues() -> list[ValidationIssue]`: `validate` sobre la spec resuelta del ítem 0, o sobre la spec cruda si no hay ítems.
    - `plan_for(i: int) -> RenderPlan`: resuelve `EDGE_COLOR` con `edge_color(load_proxy(path, 512))` y guarda ese color en caché por ítem.
    - `analyze(i: int) -> Diagnosis`: deja el ítem en ANALYZED y luego READY.
    - `approve(i)`
    - `approve_all() -> list[int]`: aprueba los ítems READY cuyo diagnóstico no sea BAJA ni MUY_BAJA y devuelve los índices que se saltó.
    - `export(indices: Sequence[int] | None, out_dir: Path, progress: Callable[[int, int], None] | None = None, today: date | None = None) -> list[ExportResult]`. Si `indices` es None, exporta todos los APPROVED. Cada ítem va en su propio `try/except`: un error deja ese ítem en ERROR y el lote continúa. La salida usa `unique_path(output_path(...))`. Un ítem exportado queda en EXPORTED con `output`. Antes de exportar, si `issues()` contiene un `error`, lanza `ValueError` con el mensaje.

- [ ] **Step 1: Pruebas.**
  - Agregar 5 imágenes válidas, 1 corrupta y 1 duplicada → 7 ítems; el corrupto en ERROR y el duplicado con `duplicate_of=0`.
  - `approve_all()` se salta el ítem MUY_BAJA.
  - `export` → un PDF por cada aprobado, los nombres `Cliente_001…` en la carpeta de la fecha, y `progress` llamado N veces con `(k, N)`.
  - Con monkeypatch, `write_pdf` falla solo para el ítem 2 → ese queda en ERROR y los demás en EXPORTED.
  - Exportar dos veces → aparecen `_2`; nada se sobrescribe.
  - Los originales conservan su SHA-256 después de exportar.
  - `set_spec(700×700)` y luego `export` → `ValueError`.
  - `move(0, 2)` reordena los ítems.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(app): controlador de trabajo con exportación tolerante a fallos`.

### Task 12: UI — ventana, tema, Inicio y Configuración

**Files:**
- Create: `src/printmaster/__main__.py`, `app.py`, `ui/theme.py`, `ui/theme.qss`, `ui/workers.py`, `ui/main_window.py`, `ui/pages/home_page.py`, `ui/pages/settings_page.py`
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `Settings`, `load_settings`, `save_settings`, `setup_logging` (T10), `load_profile`, `list_profiles` (T3), `JobController` (T11).
- Produces:
  - `apply_dark_theme(app: QApplication) -> None`: estilo Fusion, una `QPalette` oscura y el `theme.qss`, que define botones grandes (alto mínimo 36 px) y fuente de 10 pt.
  - `class Worker(QRunnable)`, que emite `Signals.done(object)` y `Signals.failed(str)`, y la función `run_async(fn, *args, on_done, on_failed) -> None` sobre `QThreadPool.globalInstance()`.
  - `class MainWindow(QMainWindow)` con `__init__(self, settings: Settings)`. La barra lateral es una `QListWidget` con objectName `nav`, con exactamente 3 entradas: "Inicio", "Nuevo trabajo" y "Configuración". La entrada se conecta a un `QStackedWidget` (`pages`). La página "Nuevo trabajo" es un `JobPage` (T16); mientras no exista, se usa un `QWidget` vacío que T16 reemplaza.
  - `HomePage`: un botón grande "Nuevo trabajo" que cambia a la página 1 y una lista de favoritos. Al hacer doble clic en un favorito, se abre "Nuevo trabajo" con ese formato (señal `favorite_chosen(FavoriteFormat)`).
  - `SettingsPage`: carpeta de salida (botón "Cambiar…" que abre `QFileDialog`), PPI por defecto, unidad por defecto, prefijo, dígitos, casilla "Organizar por fecha", lista de favoritos con botón "Eliminar favorito" y botón "Guardar". "Guardar" llama a `save_settings` y emite `settings_changed(Settings)`.
  - `main() -> int` en `app.py`: crea `QApplication`, ejecuta `setup_logging`, `apply_dark_theme` y `MainWindow`, y llama a `exec()`. Instala un `sys.excepthook` que registra el error en el log y muestra `QMessageBox.critical` con "Ocurrió un error inesperado. Detalles en el registro.". `__main__.py` llama a `raise SystemExit(main())`.

- [ ] **Step 1: Pruebas** (pytest-qt, con `PRINTMASTER_HOME=tmp_path`).
  - La barra lateral tiene exactamente las 3 entradas, en ese orden.
  - Hacer clic en "Configuración" cambia el índice del stack a 2.
  - En Configuración, cambiar el prefijo a "Pedido" y pulsar Guardar → `load_settings().naming_prefix == "Pedido"`.
  - "Eliminar favorito" deja 5 favoritos después de guardar.
  - El botón "Nuevo trabajo" de Inicio cambia el índice a 1.
- [ ] **Step 2:** Ejecutar `pytest tests/ui/test_main_window.py -q` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS. Además, `python -m printmaster` abre la ventana (verificación manual en Windows, en la Tarea 17).
- [ ] **Step 5:** Commit `feat(ui): ventana principal, tema oscuro, inicio y configuración`.

### Task 13: UI — cola de imágenes

**Files:**
- Create: `src/printmaster/ui/models/queue_model.py`, `src/printmaster/ui/widgets/queue_view.py`
- Test: `tests/ui/test_queue.py`

**Interfaces:**
- Consumes: `JobController`, `JobItem`, `ItemStatus` (T11), `make_thumbnail` (T4) y `run_async` (T12).
- Produces:
  - `class QueueModel(QAbstractListModel)` con `__init__(self, controller)`.
    - Roles: `DisplayRole` (nombre del archivo); `DecorationRole` (miniatura en caché, o un ícono de "cargando" mientras se genera); `ToolTipRole` ("{formato} · {W}×{H} px · {MB:.1f} MB", más "Duplicado de #{n}" si aplica); `StatusRole = Qt.UserRole + 1` (`ItemStatus`); `LevelRole = Qt.UserRole + 2` (`QualityLevel | None`).
    - Métodos: `refresh()`, `add_paths(paths: list[Path]) -> None` (pide las miniaturas en segundo plano), `remove_rows(rows)` y `moveRows` (hacia `controller.move`).
  - `class QueueView(QWidget)`: contiene un `QListView` en modo ícono de 96 px con *drag-drop* interno, que **acepta soltar archivos y carpetas desde el Explorador**. Tiene los botones "+ Archivos" (`QFileDialog.getOpenFileNames` con filtro de extensiones), "+ Carpeta" y "Quitar". La tecla Supr hace lo mismo que "Quitar". Emite la señal `current_changed(int)`. La insignia de estado (●Exc / ●Bue / ●Ace / ▲Baj / ▲MBaj / ✕Error / ✓Exportada) se pinta con un `QStyledItemDelegate`.

- [ ] **Step 1: Pruebas.**
  - Simular soltar (`QDropEvent` con `QMimeData` de URLs) 3 imágenes y 1 `.txt` → `rowCount == 3`.
  - Con `qtbot.waitUntil`, todas las miniaturas terminan cargadas (DecorationRole deja de ser el ícono de "cargando").
  - Seleccionar la fila 1 y pulsar Supr → `rowCount == 2`.
  - `moveRows(0→2)` cambia el orden de `controller.items`.
  - El tooltip contiene "px" y "MB".
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(ui): cola con miniaturas, arrastrar, reordenar y quitar`.

### Task 14: UI — lienzo de vista previa

**Files:**
- Create: `src/printmaster/ui/widgets/preview_canvas.py`
- Test: `tests/ui/test_preview_canvas.py`

**Interfaces:**
- Consumes: `RenderPlan`, `CropOffset`, `FitMode` (T2), `full_image_rect_pt` (T5), `PrinterProfile` (T3) y `load_proxy` (T4).
- Produces: `class PreviewCanvas(QGraphicsView)` con los métodos y señales siguientes.
  - `show_plan(proxy: QImage, plan: RenderPlan, mode: FitMode, profile: PrinterProfile, img_size: tuple[int,int]) -> None`. Dibuja, en unidades de escena = pt con el eje Y invertido:
    - la página en blanco con sombra;
    - el fondo de color si existe;
    - la imagen colocada en `dest_rect` (o en `full_image_rect_pt` si es COVER);
    - en COVER, la parte fuera de la página con un velo negro de 60 % de opacidad;
    - las líneas discontinuas de los márgenes laterales físicos del perfil (`side_margin_mm`);
    - una etiqueta con "{ancho}×{alto} cm".
  - `crop_changed = Signal(CropOffset)`: solo en COVER. Al arrastrar con el mouse, el movimiento en pt se convierte a un desplazamiento en [0,1] sobre el sobrante y se emite al soltar.
  - `zoom_in()`, `zoom_out()` y `fit()` (escala 1.25×; la rueda del mouse también hace zoom).
  - `clear()`.

- [ ] **Step 1: Pruebas.**
  - Después de `show_plan` con una página de 600×900 mm, el `sceneRect` de la página mide 1700.79×2551.18 (±0.5).
  - En COVER, `qtbot.mousePress`, `mouseMove` 200 px a la derecha y `mouseRelease` emiten `crop_changed` con `x < 0.5` (al arrastrar la imagen a la derecha se ve más de su izquierda).
  - `zoom_in` aumenta `transform().m11()`.
  - En CONTAIN, el arrastre no emite nada.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(ui): vista previa a escala con recorte arrastrable`.

### Task 15: UI — inspector de formato y tarjeta de diagnóstico

**Files:**
- Create: `src/printmaster/ui/widgets/inspector.py`, `src/printmaster/ui/widgets/diagnosis_card.py`
- Test: `tests/ui/test_inspector.py`

**Interfaces:**
- Consumes: `PrintSpec, FitMode, Background, BackgroundKind, Orientation, Unit` (T2), `FavoriteFormat`, `Settings` (T10), `ValidationIssue` (T3) y `Diagnosis` (T9).
- Produces:
  - `class Inspector(QWidget)` con `__init__(self, settings: Settings)` y los controles siguientes (por objectName):
    - `width_spin`, `height_spin` (QDoubleSpinBox de 0.1 a 10000, 2 decimales);
    - `unit_combo` (cm, mm, in): al cambiar la unidad, los valores se convierten y **no** se pierde precisión, porque el valor interno se guarda en mm;
    - `orientation_combo` (Automática, Vertical, Horizontal);
    - `favorites_combo` y el botón `save_favorite_btn` "★ Guardar formato" (pide el nombre con `QInputDialog` y emite `favorite_saved`);
    - `ppi_combo` (100, 150, 200, 250, 300, Personalizado…). "Personalizado…" muestra `ppi_spin` (50–600);
    - `mode_combo` ("Ajustar sin recortar", "Rellenar", "Recortar");
    - `background_combo` (Blanco, Color…, Color del borde, Fondo difuminado), visible solo en "Rellenar". "Color…" abre `QColorDialog`;
    - `lossless_check` "Exportar sin pérdida" (activado por defecto);
    - `issues_label`, que muestra los errores en rojo y las advertencias en ámbar.
  - Métodos: `spec() -> PrintSpec`, `mode() -> FitMode`, `background() -> Background`, `lossless() -> bool`, `set_spec(spec, unit)`, `show_issues(issues: list[ValidationIssue])` y `set_favorites(list[FavoriteFormat])`.
  - Señal `changed = Signal()`, emitida en cada cambio con un *debounce* de 150 ms usando un `QTimer`.
  - `class DiagnosisCard(QWidget)` con `show(diag: Diagnosis | None, info: ImageInfo | None)`. Muestra el tamaño original en px, el formato, el PPI efectivo, el nivel (con color), la nitidez, el ruido, la calidad JPEG estimada, las advertencias y la recomendación. Cuando el plan reduce la imagen, agrega una línea "Se reducirá a {ppi} PPI".

- [ ] **Step 1: Pruebas.**
  - Fijar 60×90 cm, cambiar `unit_combo` a mm → los spinbox muestran 600 y 900. Cambiar a in → 23.62 y 35.43. `spec().width_mm == Decimal("600")`, sin deriva después de varios cambios de unidad.
  - Elegir "Personalizado…" y poner 175 → `spec().ppi == 175`.
  - `background_combo` está oculto salvo con "Rellenar".
  - `show_issues([warning rotate])` → el texto de `issues_label` contiene "gire".
  - `changed` se emite una sola vez tras 3 cambios rápidos (`qtbot.waitSignal`).
  - `DiagnosisCard.show` con un `Diagnosis` MUY_BAJA → el texto contiene "Muy baja resolución" y "PPI".
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(ui): inspector de formato y diagnóstico`.

### Task 16: UI — página Nuevo trabajo, aprobación y exportación

**Files:**
- Create: `src/printmaster/ui/pages/job_page.py`
- Modify: `src/printmaster/ui/main_window.py` (reemplazar el `QWidget` vacío de la página 1 por `JobPage` y conectar `HomePage.favorite_chosen` con `JobPage.apply_favorite`)
- Test: `tests/ui/test_job_page.py`, `tests/ui/test_no_dead_buttons.py`

**Interfaces:**
- Consumes: T11 a T15.
- Produces: `class JobPage(QWidget)` con `__init__(self, settings: Settings, profile: PrinterProfile)`.
  - Composición: un `QSplitter` horizontal con QueueView | (PreviewCanvas + barra de zoom con −, Ajustar y +) | (Inspector + DiagnosisCard dentro de un `QScrollArea`).
  - Indicador de pasos (QLabel con "① Cargar ─ ② Formato ─ ③ Revisar ─ ④ Exportar"), resaltado según el estado: hay ítems → 2; hay ítems analizados → 3; hay aprobados → 4.
  - Barra inferior: `QProgressBar` (`progress`) y los botones "Aprobar seleccionada" (`approve_btn`), "Aprobar todo" (`approve_all_btn`) y "Exportar PDF" (`export_btn`). "Exportar PDF" solo está habilitado si hay aprobados y no hay errores de validación.
  - Flujo:
    - Al agregar imágenes, cada una se analiza en segundo plano con `run_async(controller.analyze, i)` y se refrescan el modelo y la tarjeta.
    - `Inspector.changed` → `controller.set_spec/mode/background` y `export_options`; luego se recalcula **solo** el plan del ítem actual y se redibuja el lienzo. Se vuelve a analizar en segundo plano porque cambia el PPI efectivo.
    - `PreviewCanvas.crop_changed` → `controller.set_crop` y se redibuja.
    - "Aprobar todo": si se saltó algún ítem, muestra `QMessageBox.information` con "Se omitieron {n} imágenes con baja resolución. Revíselas y apruébelas una por una."
    - "Exportar PDF": usa como carpeta `settings.output_dir`. Ejecuta `controller.export` en `run_async` con progreso (se emite por señal hacia la barra) y, al terminar, muestra "{ok} PDF generados, {err} con error." junto con un botón "Abrir carpeta" (`QDesktopServices.openUrl`).
  - `apply_favorite(f: FavoriteFormat)` coloca el formato en el inspector.
  - Al cambiar de ítem en la cola se actualizan el lienzo, el inspector (el crop es por ítem) y la tarjeta.

- [ ] **Step 1: Pruebas.**
  - `test_job_page`: soltar 3 imágenes (una de 300×200 px) y esperar a que las tres queden en READY. Pulsar "Aprobar todo" con el `QMessageBox` simulado → 2 aprobadas. Pulsar "Exportar PDF" con `settings.output_dir=tmp_path` y esperar → 2 PDF en `tmp_path/<fecha>/`, cuyo MediaBox coincide con el inspector (±0.01 pt). La barra de progreso termina en 100.
  - Formato 700×700 → `export_btn` deshabilitado y el texto de issues contiene "Ningún lado".
  - `test_no_dead_buttons`: recorrer todos los `QPushButton` y `QToolButton` visibles de `MainWindow` en sus 3 páginas y verificar con `receivers(SIGNAL("clicked()")) > 0` que **ninguno** está sin conectar (regla 3 de la especificación).
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar `pytest -q` (la suite completa) → PASS, y `ruff check .` limpio.
- [ ] **Step 5:** Commit `feat(ui): flujo completo de nuevo trabajo con aprobación y exportación`.

### Task 17: Verificación en Windows y cierre de la Fase 1

**Files:**
- Create: `docs/acceptance/fase1-checklist.md`
- Modify: `PROGRESS.md`, `README.md`

- [ ] **Step 1:** Hacer push y confirmar que el CI queda en verde en `windows-latest` y en `ubuntu-latest` (`gh run watch`).
- [ ] **Step 2:** Escribir `fase1-checklist.md` para que Camilo lo ejecute en su PC:
  1. Instalar Python 3.12.
  2. `git clone` del repositorio.
  3. `py -3.12 -m venv .venv`.
  4. `.venv\Scripts\pip install -e .`
  5. `.venv\Scripts\python -m printmaster`.
  6. Arrastrar 20 imágenes reales.
  7. Formato 60×90.
  8. Probar los tres modos.
  9. Exportar.
  10. Abrir 3 PDF en Acrobat → Archivo › Propiedades: el tamaño de página es 60 × 90 cm.
  11. Imprimir 1 pieza a "Tamaño real" y medirla con una regla (tolerancia ±1 mm).
  12. Anotar tiempos y fallos.
- [ ] **Step 3:** En `README.md`: comandos exactos de instalación, ejecución y pruebas, y la ubicación de la configuración, los logs y la salida.
- [ ] **Step 4:** En `PROGRESS.md`: Fase 1 hecha (pendiente de la validación del usuario) y la Fase 2 como siguiente.
- [ ] **Step 5:** Commit `docs: checklist de aceptación Fase 1 y registro de avance` y push. **No** declarar la Fase 1 terminada hasta que Camilo confirme el checklist.
