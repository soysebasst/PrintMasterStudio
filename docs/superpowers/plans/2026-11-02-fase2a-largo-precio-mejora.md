# Fase 2A — Lámina 60 cm, largo automático, precio sugerido y mejora local — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El ancho de la lámina queda fijo en 60 cm y el largo se ajusta automáticamente a cada imagen (redondeado de 5 en 5 cm). Cada pieza muestra su precio sugerido, y las imágenes de baja calidad se mejoran localmente con Real-ESRGAN.

**Architecture:**
- `core/pricing.py` y `layout.auto_length_mm()` son funciones puras.
- La mejora vive en `core/enhance/`: un envoltorio de subprocess para el ejecutable, un instalador, un motor conservador y un orquestador con caché.
- `JobController` decide qué fuente usar (original o mejorada) y la UI solo muestra el resultado. Los PDF, la vista previa y el precio salen del mismo `RenderPlan`.

**Tech Stack:** se mantiene el de la Fase 1. Se usan `subprocess`, `zipfile`, `hashlib` y `urllib.request` de la biblioteca estándar, sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-02-fase2a-largo-precio-mejora-design.md` (y la especificación base `2026-11-02-printmaster-studio-design.md`).

## Global Constraints

- Ancho de rollo por defecto: `roll_width_mm = 600`. El largo automático se redondea hacia arriba al múltiplo de **50 mm**, con un mínimo de 50 mm.
- Precio: `largo_eq = largo_mm × ancho_mm / 600`; `precio = 10.000 + (largo_eq − 450) × 5.000 / 450`. Se redondea **al $1.000 más cercano con ROUND_HALF_UP** (`Decimal`) y luego se aplica el mínimo `max(10.000, ·)`. Todo debe ser configurable.
- Modo nuevo y por defecto: `FitMode.FIT_LENGTH = "largo_auto"`, con la etiqueta "Ajustar largo a la imagen". Orientación nueva y por defecto: `Orientation.AS_ENTERED = "as_entered"`, con la etiqueta "Como se escribió".
- Favoritos por defecto: `60×30, 60×45, 60×60, 60×90, 60×120, 60×150` (cm). Los favoritos ya guardados **no se tocan**.
- Mejora: objetivo de **150 PPI**, pasadas ×4 con **máximo 2**, lado mayor de **12000 px** como máximo tras cada pasada, caché PNG en `data_dir()/cache/enhanced/<sha256>_<modelo>_<pasadas>.png`.
- Modelos: `realesrgan-x4plus` (fotos) y `realesrgan-x4plus-anime` (ilustraciones). Se usa el anime si el proxy, cuantizado a 5 bits por canal, tiene **menos de 4096** colores distintos.
- URL del motor: `https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip`, SHA-256 `e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96`. Se instala en `data_dir()/engines/realesrgan/`.
- La mejora nunca modifica el original. La UI nunca dice "alta resolución original" de una imagen mejorada.
- Todos los textos en español. Ningún botón queda sin función (la prueba `test_no_dead_buttons` debe seguir pasando).
- Commits con el pie `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **`settings.json` guardado por la Fase 1**, con `default_mode="ajustar"` y sin los campos nuevos: al cargarlo, el modo por defecto pasa a FIT_LENGTH y el ancho a 60, sin perder el prefijo, la carpeta ni los favoritos del usuario. → prueba en la Tarea 2.
2. **Imágenes panorámicas extremas** (3000×100 → lámina de 50 mm) y **muy altas** (100×20000 → 120 m): no se cae. El largo de 120 m supera el máximo de 5080 mm y aparece el error de validación. → pruebas en las Tareas 1 y 4.
3. **Motor ausente, sin Vulkan o que falla a mitad de la mejora**: la imagen sigue usable con su original (o con el motor conservador) y se muestra un mensaje claro; nunca queda "Mejorando…" para siempre. → pruebas en las Tareas 5 y 6.
4. **Cambiar de formato después de mejorar**: no se vuelve a ejecutar la IA si alcanza (caché), y el PPI y el precio se recalculan al instante. → pruebas en las Tareas 6 y 7.
5. **Descarga del motor dañada o con hash distinto**: no se instala, no deja archivos a medias y muestra el error. → prueba en la Tarea 5.

---

## Mapa de archivos

```
src/printmaster/core/pricing.py                  (nuevo)
src/printmaster/core/layout.py                   (FIT_LENGTH, auto_length_mm)
src/printmaster/domain/models.py                 (FitMode.FIT_LENGTH, Orientation.AS_ENTERED, EnhanceChoice)
src/printmaster/infra/settings.py                (campos nuevos y migración)
src/printmaster/core/enhance/__init__.py         (nuevo)
src/printmaster/core/enhance/realesrgan.py       (nuevo: envoltorio del ejecutable)
src/printmaster/core/enhance/installer.py        (nuevo: descarga, verificación y extracción)
src/printmaster/core/enhance/conservative.py     (nuevo: Lanczos + enfoque)
src/printmaster/core/enhance/enhancer.py         (nuevo: pasadas, modelo, caché)
src/printmaster/app_services/job_controller.py   (fuente mejorada, precio, página por ítem)
src/printmaster/ui/widgets/inspector.py · diagnosis_card.py · preview_canvas.py
src/printmaster/ui/pages/job_page.py · settings_page.py
tests/fakes/fake_realesrgan.py                   (nuevo: ejecutable falso)
```

---

### Task 1: Dominio — largo automático y precio

**Files:**
- Modify: `src/printmaster/domain/models.py`, `src/printmaster/core/layout.py`
- Create: `src/printmaster/core/pricing.py`
- Test: `tests/unit/test_auto_length.py`, `tests/unit/test_pricing.py`

**Interfaces:**
- Produces:
  - En `models.py`: `FitMode.FIT_LENGTH = "largo_auto"`. `Orientation.AS_ENTERED = "as_entered"`: `PrintSpec.resolved_for` devuelve la spec con el ancho y el alto tal como vienen. `class EnhanceChoice(StrEnum): AUTO="auto"; ON="on"; OFF="off"`.
  - `layout.auto_length_mm(width_mm: Decimal, img_w: int, img_h: int, step_mm: int = 50) -> Decimal`: `ceil(width·h/w / step)·step`, con un mínimo de `step`. Hay que restar un épsilon de 1e-9 antes del techo, para que 600·554/554 dé exactamente 600.
  - `layout.plan(..., length_step_mm: int = 50)`: en modo FIT_LENGTH, la página es `spec.width_mm × auto_length_mm(spec.width_mm, W, H, step)`, sin rotación, y luego el mismo cálculo que CONTAIN (centrado, fondo blanco).
  - `layout.page_size_mm(info: ImageInfo, spec: PrintSpec, mode: FitMode, length_step_mm: int = 50) -> tuple[Decimal, Decimal]` devuelve el tamaño de la página resuelta y se usa para el precio y la validación.
  - En `pricing.py`:
    - `@dataclass(frozen=True) PricingConfig(ref_short_mm: int = 450, price_short: int = 10000, ref_long_mm: int = 900, price_long: int = 15000, min_price: int = 10000, round_to: int = 1000, base_width_mm: int = 600)`
    - `suggest_price(width_mm: Decimal, length_mm: Decimal, cfg: PricingConfig = PricingConfig()) -> int`
    - `format_cop(value: int) -> str` → `"$17.000"`

- [ ] **Step 1: Pruebas.**
  - `auto_length_mm(D(600), w, h)` para (554,554)→600, (236,420)→1100, (4000,3000)→450, (3000,4500)→900, (1000,3000)→1800, (3000,1000)→200, (3000,100)→50.
  - Con hypothesis: el resultado es ≥ el exacto, menor que exacto + 50 y múltiplo de 50.
  - `plan(info(236,420), PrintSpec(D(600), D(900)), FitMode.FIT_LENGTH)` tiene página `(600, 1100)`, `dest_w == page_w_pt` y la imagen centrada en vertical.
  - El mismo plan con `Orientation.AS_ENTERED` y una imagen horizontal (4000×3000) da una página de 600×450, sin girar.
  - `PrintSpec(D(600), D(900), orientation=Orientation.AS_ENTERED).resolved_for(4000, 3000)` conserva (600, 900).
  - Precios: `suggest_price(D(600), L)` con L = 450→10000, 900→15000, 600→12000, 1100→17000, 1800→25000, 200→10000. `suggest_price(D(300), D(900)) == 10000`. Caso de empate: con `PricingConfig(price_short=10500)`, `suggest_price(D(600), D(450)) == 11000` (10.500 sube). Configurable: `PricingConfig(price_long=20000)` con 900 → 20000.
  - `format_cop(17000) == "$17.000"`.
- [ ] **Step 2:** `pytest tests/unit/test_auto_length.py tests/unit/test_pricing.py -q` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS. Luego `pytest -q`, que debe dar todo verde.
- [ ] **Step 5:** Commit `feat: largo automático (ancho de rollo fijo) y precio sugerido`.

### Task 2: Configuración — ancho de rollo, precios, mejora y migración

**Files:**
- Modify: `src/printmaster/infra/settings.py`
- Test: `tests/unit/test_settings.py` (agregar pruebas)

**Interfaces:**
- Consumes: `FitMode.FIT_LENGTH`, `Orientation`, `PricingConfig` (T1).
- Produces:
  - Campos nuevos de `Settings`:
    - `settings_version: int = 2`
    - `roll_width_mm: int = 600` (rango 210–610)
    - `length_step_mm: int = 50` (rango 1–500)
    - `default_mode` pasa a FIT_LENGTH
    - `default_orientation: Orientation = AS_ENTERED`
    - `price_short: int = 10000`, `price_long: int = 15000`, `ref_short_mm: int = 450`, `ref_long_mm: int = 900`, `min_price: int = 10000`, `price_round_to: int = 1000`
    - `enhance_enabled: bool = True`, `enhance_target_ppi: int = 150` (rango 72–300)
  - `Settings.pricing() -> PricingConfig`
  - Favoritos por defecto: `60 × 30 cm … 60 × 150 cm` (los seis de las Global Constraints).
  - Migración en `load_settings`: si el JSON no trae `settings_version` o trae un valor < 2, se fija `default_mode=FIT_LENGTH`, `default_orientation=AS_ENTERED` y `settings_version=2`. Los demás campos (prefijo, carpeta, favoritos) se conservan.

- [ ] **Step 1: Pruebas.**
  - `test_v1_settings_migrated`: escribir el JSON de la Fase 1 `{"output_dir": "...", "default_ppi": 200, "default_unit": "cm", "default_mode": "ajustar", "naming_prefix": "Pedido", "favorites": [{"name": "Mío", "width": 50, "height": 70, "unit": "cm"}]}`. Al cargarlo: `default_mode == FIT_LENGTH`, `roll_width_mm == 600`, `naming_prefix == "Pedido"` y `[f.name for f in favorites] == ["Mío"]`.
  - `test_new_default_favorites`: los nombres de los favoritos por defecto son exactamente los seis de 60 de ancho.
  - `test_pricing_config`: `Settings(price_long=20000).pricing().price_long == 20000`.
  - `test_roll_width_range`: `Settings(roll_width_mm=700)` genera `ValidationError`.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS; la suite completa también.
- [ ] **Step 5:** Commit `feat(config): ancho de rollo, precios, mejora y migración desde Fase 1`.

### Task 3: Ejecutable falso de Real-ESRGAN para pruebas

**Files:**
- Create: `tests/fakes/__init__.py`, `tests/fakes/fake_realesrgan.py`
- Test: `tests/unit/test_fake_realesrgan.py`

**Interfaces:**
- Produces: un script que se ejecuta como `[sys.executable, path_to_fake, *args]` y acepta la misma interfaz de línea de comandos que el motor real: `-i in -o out -n modelo -s 4 -t tile -f png -g gpu`.
  - Comportamiento: abre la entrada con Pillow, la escala ×4 con BICUBIC y la guarda en PNG. Escribe `"fake: <modelo>"` en stderr. Termina con código 0.
  - Variables de entorno de control:
    - `FAKE_ESRGAN_FAIL=1` → código 255 y "vkCreateInstance failed" en stderr (simula que no hay Vulkan);
    - `FAKE_ESRGAN_SLEEP=<s>` → duerme antes de escribir la salida;
    - `FAKE_ESRGAN_LOG=<archivo>` → agrega una línea por invocación.
  - Fixture `fake_engine_cmd` en `tests/conftest.py`, que devuelve `[sys.executable, str(fake_path)]`.

- [ ] **Step 1:** Prueba `test_fake_scales_x4`: ejecutar el falso con una imagen de 10×8 → la salida mide 40×32 y el código es 0. Prueba `test_fake_fail`: con `FAKE_ESRGAN_FAIL=1` el código es ≠ 0.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `test: ejecutable falso de Real-ESRGAN`.

### Task 4: Página por ítem, precio y validación en el controlador

**Files:**
- Modify: `src/printmaster/app_services/job_controller.py`
- Test: `tests/integration/test_job_controller_fase2a.py`

**Interfaces:**
- Consumes: T1 y T2.
- Produces:
  - `JobController` toma el spec inicial de `settings.roll_width_mm` × 900, con `settings.default_orientation` y `settings.default_mode`.
  - `page_size_for(i: int) -> tuple[Decimal, Decimal]`, que usa `layout.page_size_mm` con la fuente efectiva (T6) y `settings.length_step_mm`.
  - `price_for(i: int) -> int | None`: `None` si el ítem no tiene info.
  - `total_price(indices: Iterable[int] | None = None) -> tuple[int, int]`: devuelve `(cantidad, suma)` sobre los ítems con info que no están en ERROR. Con `None` toma todos.
  - `issues(i)` valida la página resuelta del ítem (incluido FIT_LENGTH).
  - `export()` usa el mismo `length_step_mm` congelado en `JobParams`; se agrega el campo `length_step_mm: int`.

- [ ] **Step 1: Pruebas.**
  - Con el modo FIT_LENGTH por defecto y las imágenes 554×554 y 236×420: `price_for` da 12000 y 17000, y `total_price() == (2, 29000)`.
  - Exportar las dos → MediaBox de 600×600 y 600×1100 mm (±0.01 pt).
  - Una imagen de 100×20000 → `issues(0)` contiene `too_long`.
  - Una imagen de 3000×100 → página de 600×50 y precio de 10000.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS; la suite completa también, ajustando las pruebas de la Fase 1 que fijan `PrintSpec` sin modo para que pasen modo y orientación explícitos.
- [ ] **Step 5:** Commit `feat(app): página por ítem, precio sugerido y total del lote`.

### Task 5: Motor Real-ESRGAN, motor conservador e instalador

**Files:**
- Create: `src/printmaster/core/enhance/__init__.py`, `realesrgan.py`, `conservative.py`, `installer.py`
- Test: `tests/unit/test_realesrgan.py`, `tests/unit/test_installer.py`, `tests/unit/test_conservative.py`

**Interfaces:**
- Consumes: `paths.data_dir()` y el falso de T3.
- Produces:
  - `class EnhanceError(Exception)`: mensaje en español que incluye las últimas líneas de stderr.
  - `class EnhanceCancelled(EnhanceError)`
  - `MODEL_PHOTO = "realesrgan-x4plus"`, `MODEL_ART = "realesrgan-x4plus-anime"`
  - `class RealEsrgan`, con `__init__(self, command: list[str], timeout_s: int = 600)` y los métodos:
    - `upscale_x4(src: Path, dst: Path, model: str, tile: int = 0, cancel: threading.Event | None = None) -> None`: ejecuta `command + ["-i", src, "-o", dst, "-n", model, "-s", "4", "-t", str(tile), "-f", "png"]`. Revisa `cancel` cada 0.2 s y, si está activado, mata el proceso y lanza `EnhanceCancelled`. Si el código es ≠ 0 o falta la salida, lanza `EnhanceError`. En Windows usa `creationflags=CREATE_NO_WINDOW`.
    - `self_test(tmp_dir: Path) -> tuple[bool, str]`: escala una imagen de 64×64. Devuelve `(True, "Motor listo")`, o `(False, mensaje)`; si el stderr contiene "vk" o "vulkan", el mensaje es exactamente "Su equipo no tiene aceleración compatible; se usará la mejora básica (más rápida, menos detalle)."
  - `default_engine_dir() -> Path` = `data_dir()/"engines"/"realesrgan"`, y `find_engine(dir: Path | None = None) -> RealEsrgan | None`, que busca `realesrgan-ncnn-vulkan.exe` (o sin extensión fuera de Windows) en `dir` o en sus subcarpetas.
  - `ENGINE_URL` y `ENGINE_SHA256` con los valores de las Global Constraints.
  - `install_engine(dest: Path | None = None, url: str = ENGINE_URL, sha256: str = ENGINE_SHA256, opener: Callable[[str], BinaryIO] = urllib.request.urlopen, progress: Callable[[int, int], None] | None = None) -> Path`. Pasos:
    1. descarga a `dest/.download.zip.tmp`;
    2. verifica el SHA-256 (si no coincide: borra el temporal y lanza `EnhanceError("La descarga no coincide con el archivo oficial (hash distinto). No se instaló.")`);
    3. extrae a `dest/.staging`, valida que el ejecutable exista y luego `os.replace` a `dest/current`;
    4. devuelve la ruta del ejecutable.
  - `upscale_conservative(img: Image.Image, factor: int) -> Image.Image`: Lanczos más `ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3)`.

- [ ] **Step 1: Pruebas.**
  - Con el falso, `upscale_x4` de una imagen de 20×10 da 80×40.
  - Con `FAKE_ESRGAN_FAIL=1` → `EnhanceError`, y `self_test` devuelve `False` con el mensaje exacto de Vulkan.
  - Cancelar: con `FAKE_ESRGAN_SLEEP=5`, activar el evento a los 0.3 s → `EnhanceCancelled` en menos de 2 s.
  - Instalador: construir un zip local con `realesrgan-ncnn-vulkan-20220424-windows/realesrgan-ncnn-vulkan.exe` y un `models/` falso, servirlo con un `opener` falso (un `BytesIO`) y pasar su sha → `find_engine(dest)` no es `None`.
  - Hash distinto → `EnhanceError` y en `dest` no queda ni `.download.zip.tmp` ni `current`.
  - `upscale_conservative` de 10×10 con factor 4 da 40×40.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(enhance): motor Real-ESRGAN, respaldo conservador e instalador verificado`.

### Task 6: Orquestador de mejora con caché e integración en el controlador

**Files:**
- Create: `src/printmaster/core/enhance/enhancer.py`
- Modify: `src/printmaster/app_services/job_controller.py`
- Test: `tests/unit/test_enhancer.py`, `tests/integration/test_enhance_flow.py`

**Interfaces:**
- Consumes: T4 y T5, `probe` y `load_proxy`.
- Produces:
  - `passes_needed(src_ppi: float, target_ppi: float, max_passes: int = 2) -> int` (0 si `src_ppi ≥ target_ppi`).
  - `choose_model(proxy: Image.Image) -> str`, con el umbral de 4096 colores a 5 bits por canal.
  - `@dataclass(frozen=True) EnhanceResult(path: Path, model: str, passes: int, engine: str)`, donde `engine` vale `"Real-ESRGAN"` o `"Mejora básica"`.
  - `class Enhancer`, con `__init__(self, engine: RealEsrgan | None, cache_dir: Path)` y el método `enhance(src: Path, sha256: str, passes: int, model: str, cancel: threading.Event | None = None, progress: Callable[[int, int], None] | None = None) -> EnhanceResult`.
    - Si ya existe `cache_dir/f"{sha}_{model}_{passes}.png"`, devuelve sin procesar.
    - Si no: por cada pasada llama a `upscale_x4` (o, sin motor, a `upscale_conservative`) sobre un PNG intermedio en `cache_dir/tmp`. Tras cada pasada reduce el lado mayor a 12000 px si lo supera, y luego hace `os.replace` al archivo de caché. Llama a `progress(k, passes)`.
    - Si el motor falla a mitad, hace un **solo** reintento con el motor conservador y deja `engine="Mejora básica"`.
  - Cambios en `JobItem`: se agregan `enhance_choice: EnhanceChoice = AUTO`, `enhanced: EnhanceResult | None = None`, `enhanced_info: ImageInfo | None = None` y `enhancing: bool = False`.
  - Métodos de `JobController`:
    - `source_info(i) -> ImageInfo`: `enhanced_info` si existe y la opción no es OFF; si no, `info`.
    - `needs_enhancement(i) -> int`: el número de pasadas. Es 0 si la opción es OFF, si ya está mejorada o si la mejora está desactivada en la configuración y la opción es AUTO. Con ON, al menos 1 pasada. Con AUTO, solo si el nivel base es BAJA o MUY_BAJA, y entonces `passes_needed(ppi_del_original, settings.enhance_target_ppi)`.
    - `enhance(i, enhancer, cancel=None, progress=None) -> EnhanceResult`: mientras corre, `enhancing=True`. Al terminar guarda `enhanced` y `enhanced_info = probe(result.path)` y recalifica. Si falla, deja `item.error` con el mensaje y el ítem sigue en READY con su original.
    - `set_enhance_choice(i, choice)`.
  - `plan_for`, `analyze`, `_rerate`, `price_for`, `page_size_for` y `export` usan `source_info(i)` en lugar de `info`.

- [ ] **Step 1: Pruebas.**
  - `passes_needed(10, 150) == 2`, `passes_needed(50, 150) == 1`, `passes_needed(160, 150) == 0`, `passes_needed(2, 150) == 2` (tope).
  - `choose_model` de una ilustración de 4 colores sólidos → `MODEL_ART`; con la textura de `conftest` → `MODEL_PHOTO`.
  - `Enhancer` con el falso: una imagen de 236×420 con 2 pasadas da un PNG de 3776×6720, y el log del falso tiene 2 líneas. Una segunda llamada usa la caché (el log sigue con 2 líneas).
  - Una imagen de 4000×3000 con 2 pasadas → el lado mayor del resultado es ≤ 12000.
  - Con `engine=None` → 1 pasada da ×4 y `engine == "Mejora básica"`.
  - Si el motor falla → resultado con `"Mejora básica"`, sin excepción.
  - Integración: una imagen de 236×420 en FIT_LENGTH, tras analizar, tiene `needs_enhancement(0) == 2`. Tras `enhance(0, Enhancer(fake, tmp))`: `source_info(0).width_px == 3776`, el nivel es ≥ ACEPTABLE, la página sigue en 600×1100, el precio sigue en 17000 y el export genera un PDF de 600×1100 mm cuya imagen incrustada mide ≥ 3500 px de ancho. El SHA-256 del original no cambia.
  - Con `set_enhance_choice(0, OFF)`, `source_info` vuelve al original.
  - Cambiar el formato después de mejorar no vuelve a ejecutar el motor (el log no cambia) y el precio se actualiza al instante.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS; la suite completa también.
- [ ] **Step 5:** Commit `feat(enhance): orquestador con caché e integración en el trabajo`.

### Task 7: UI — inspector, tarjeta de diagnóstico y precio

**Files:**
- Modify: `src/printmaster/ui/widgets/inspector.py`, `diagnosis_card.py`
- Test: `tests/ui/test_inspector.py` (agregar pruebas)

**Interfaces:**
- Consumes: T1, T2 y T6.
- Produces:
  - Inspector:
    - `MODE_LABELS` agrega en primer lugar `(FitMode.FIT_LENGTH, "Ajustar largo a la imagen")`, que es el valor por defecto según `settings.default_mode`.
    - Agrega la orientación `(Orientation.AS_ENTERED, "Como se escribió")` en primer lugar.
    - El ancho inicial es `settings.roll_width_mm`.
    - En FIT_LENGTH, `height_spin` queda en solo lectura y con el sufijo " (calculado)". El método `set_calculated_length(mm: Decimal | None)` muestra el largo de la imagen actual.
    - Combo `enhance_combo`, con las opciones "Mejora: Automática", "Mejorar con IA" y "No mejorar" (datos `EnhanceChoice`), y la señal `enhance_choice_changed(object)`.
  - `DiagnosisCard.show_diagnosis(..., price: int | None = None, page_mm: tuple[Decimal, Decimal] | None = None, enhanced: tuple[ImageInfo, EnhanceResult] | None = None, enhancing: bool = False)`. Muestra, según el caso:
    - `"Lámina: 60 × 110 cm · Precio sugerido: $17.000"`;
    - `"Mejorada con IA (Real-ESRGAN, 2 pasadas): 3776×6720 px"` o `"Mejorada (Mejora básica)…"`;
    - `"Mejorando con IA…"` mientras `enhancing` es verdadero.

- [ ] **Step 1: Pruebas.**
  - El modo por defecto es FIT_LENGTH y el ancho inicial es 60 cm.
  - En FIT_LENGTH, `height_spin.isReadOnly()`; en CONTAIN no lo es.
  - `set_calculated_length(D(1100))` muestra 110 en cm.
  - `enhance_combo` emite `enhance_choice_changed` con `EnhanceChoice.OFF`.
  - La tarjeta con `price=17000` y `page_mm=(600, 1100)` contiene "60 × 110 cm" y "$17.000". Con `enhanced` contiene "Mejorada con IA" y nunca "alta resolución".
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat(ui): modo largo automático, precio y estado de mejora en inspector y diagnóstico`.

### Task 8: UI — página de trabajo (cola de mejora, antes/después, total) y Configuración

**Files:**
- Modify: `src/printmaster/ui/pages/job_page.py`, `src/printmaster/ui/widgets/preview_canvas.py`, `src/printmaster/ui/pages/settings_page.py`, `src/printmaster/ui/models/queue_model.py`
- Test: `tests/ui/test_job_page_fase2a.py`, `tests/ui/test_settings_page_fase2a.py`

**Interfaces:**
- Consumes: T4 a T7.
- Produces:
  - `JobPage`:
    - Usa `self.enhancer = Enhancer(find_engine(), data_dir()/"cache"/"enhanced")`. En pruebas se inyecta con `JobPage(settings, profile, enhancer=...)`.
    - Al terminar el análisis, si `needs_enhancement(i) > 0` y `settings.enhance_enabled`, el ítem entra en una cola de mejora **secuencial**: un solo `run_async` a la vez, con `owner=self`.
    - El botón `cancel_enhance_btn`, "Cancelar mejora", está visible solo mientras hay mejoras pendientes y activa el `threading.Event`.
    - Etiqueta `total_label` en la barra inferior: "N láminas · $X", a partir de `controller.total_price()`.
    - Botón `before_after_btn` ("Ver original" / "Ver mejorada") en la barra de zoom, habilitado solo si el ítem actual está mejorado. Llama a `PreviewCanvas.show_plan` con el proxy del original o de la versión mejorada; el plan es el mismo.
    - "Exportar PDF" queda deshabilitado mientras hay mejoras en curso.
    - "Aprobar todo" muestra, además del aviso de omitidas, "Se mejoraron {n} imágenes con IA: revíselas con «Ver original / Ver mejorada»." si n > 0.
  - `QueueModel`: la insignia agrega "IA" (color #8e44ad) cuando el ítem está mejorado, y "…IA" mientras se mejora.
  - `SettingsPage`, con una sección nueva **"Precios"**: `price_short_spin`, `price_long_spin` y `min_price_spin` (pasos de 500) y `roll_width_spin` (en cm, 21–61).
  - `SettingsPage`, con una sección nueva **"Mejora con IA"**:
    - `enhance_check` ("Mejorar automáticamente imágenes de baja calidad") y `target_ppi_spin`;
    - `engine_status_label` ("Motor instalado y listo" / "No instalado" / el mensaje de Vulkan);
    - `install_engine_btn` "Instalar motor de mejora", que llama a `install_engine` en `run_async` con progreso y luego a `self_test`, y muestra el resultado;
    - `test_engine_btn` "Probar motor".
    - Emite `engine_changed()` para que `JobPage` recargue el motor con `find_engine()`.

- [ ] **Step 1: Pruebas.**
  - `test_enhance_flow_ui`: inyectar un `Enhancer` con el falso y la vista en FIT_LENGTH. Soltar una imagen de 236×420 → esperar a que esté mejorada (`controller.items[0].enhanced` no es None) → el texto de la tarjeta contiene "Mejorada con IA", `total_label` contiene "$17.000", `before_after_btn` está habilitado y al hacer clic su texto cambia.
  - `test_export_disabled_while_enhancing`: con `FAKE_ESRGAN_SLEEP=2`, `export_btn` está deshabilitado durante la mejora.
  - `test_cancel_enhance`: con `FAKE_ESRGAN_SLEEP=5`, clic en "Cancelar mejora" → en menos de 3 s el ítem queda con `enhancing False`, sin mejora, READY y usable.
  - Configuración: cambiar `price_long_spin` a 20000 y guardar → `load_settings().price_long == 20000`.
  - `install_engine_btn` con `install_engine` sustituido por monkeypatch (`lambda **k: fake_exe`) y `self_test` sustituido → `engine_status_label` contiene "listo".
  - `test_no_dead_buttons` sigue en verde, con los botones nuevos incluidos.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** `pytest -q` completo → PASS, y `ruff check .` limpio.
- [ ] **Step 5:** Commit `feat(ui): cola de mejora, antes/después, total del lote y configuración de precios y motor`.

### Task 9: Verificación, documentación y prueba real del motor

**Files:**
- Modify: `README.md`, `PROGRESS.md`, `docs/acceptance/fase1-checklist.md` (renombrar a `aceptacion.md` y agregar la sección de la Fase 2A)
- Test: `tests/integration/test_realesrgan_real.py`, marcada `@pytest.mark.gpu` y omitida si `find_engine()` devuelve None

- [ ] **Step 1:** Escribir la prueba `@gpu` `test_real_engine_upscales`: con el motor real instalado, una imagen de 64×64 da 256×256. Registrar el marcador `gpu` en `pyproject` y agregar `-m "not gpu"` por defecto en CI.
- [ ] **Step 2:** Capturas de pantalla (offscreen) con las imágenes de prueba de Camilo, usando el motor falso para revisar el diseño. Verificar que sale 60×60 con $12.000, 60×110 con $17.000 y las insignias "IA".
- [ ] **Step 3:** Push y CI verde en Windows y Linux.
- [ ] **Step 4:** Checklist para Camilo:
  - actualizar con `git pull` y `pip install -e .`;
  - en Configuración, pulsar "Instalar motor de mejora" y anotar el mensaje;
  - cargar las dos imágenes de prueba y comparar antes y después;
  - exportar e imprimir una a "Tamaño real";
  - anotar el tiempo de mejora por imagen;
  - correr `pytest -m gpu -q` y anotar el resultado.
- [ ] **Step 5:** Commit `docs: aceptación Fase 2A` y la revisión final de la rama.
