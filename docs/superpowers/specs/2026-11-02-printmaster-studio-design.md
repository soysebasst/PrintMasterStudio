# PrintMaster Studio — Plan técnico v1

**Estado:** propuesta para aprobación (todavía no hay código)
**Fecha:** 2 nov 2026 · **Impresora objetivo:** Epson SureColor SC-T3170 (24")

---

## 0. Lo que entendí (corrígeme si algo está mal)

**Lo que dijiste:**
- Hoy cada imagen pasa por Canva → documento al tamaño → ajuste → PDF → impresión. Con 300–500 imágenes al mes eso es un cuello de botella.
- Quieres una app de escritorio para Windows que cargue lotes, diagnostique la calidad real, ajuste la imagen a **cualquier** tamaño físico y genere **un PDF por imagen** con dimensiones exactas.
- La IA es opcional, local por defecto, y Gemini es un complemento con consentimiento y control de gasto.
- No se deben alterar textos, logos, rostros ni marcas del cliente sin necesidad.
- La app tiene que poder instalarse en un PC sin Python, y debe ser estable por encima de vistosa.

**Decisiones confirmadas (2 nov 2026):**
- D1. Uso **solo en los PCs de mesa propios**. No hay venta por ahora: sin certificado de firma de código ni sistema de licencias. Igual se mantienen fuera las librerías AGPL por si eso cambia.
- D2. **La GPU no se conoce todavía.** No es requisito: las fases 1, 2, 4 y 5 no usan GPU, y la fase 3 detecta lo que haya (GPU dedicada, gráficos integrados con Vulkan o solo CPU).
- D3. Hay **cuenta de GitHub**: repositorio privado con CI en Windows.

**Lo que supongo (confírmalo):**
- S1. Primero la usarás tú en tu negocio (1–3 PCs). Venderla a terceros sería algo posterior, pero desde ya evito librerías con licencias que lo impidan (ver §3).
- S2. El PDF se imprime desde Acrobat o desde el driver Epson a "tamaño real". La app no envía trabajos a la impresora.
- S3. Windows 10/11 de 64 bits.
- S4. El criterio de éxito es pasar de "N minutos por imagen en Canva" a "arrastrar 50 imágenes, revisar y exportar en unos minutos", con PDF exactos al milímetro.

---

## 1. Arquitectura definitiva

Uso capas con dependencias en un solo sentido. **El núcleo no importa Qt**: así se puede probar con pytest sin interfaz y los motores se pueden cambiar sin tocar la UI.

```
┌──────────────────────────────────────────────────────────┐
│ UI (PySide6, Qt Widgets)  — vistas, modelos Qt, diálogos  │
├──────────────────────────────────────────────────────────┤
│ Aplicación — JobController, BatchRunner, HistoryService   │  ← orquesta y emite señales
├──────────────────────────────────────────────────────────┤
│ Núcleo (Python puro)                                      │
│  domain: PrintSpec, ImageItem, FitMode, RenderPlan…       │
│  services: loader, analyzer, layout, composer, pdf_writer │
├──────────────────────────────────────────────────────────┤
│ Motores (plugins, interfaz común EnhancerEngine)          │
│  conservative (Pillow/OpenCV) · realesrgan · gemini       │
├──────────────────────────────────────────────────────────┤
│ Infraestructura — SQLite, settings, keyring, logs, caché  │
└──────────────────────────────────────────────────────────┘
```

**Decisiones clave y por qué:**

| Decisión | Elección | Motivo |
|---|---|---|
| UI | Qt Widgets + estilo Fusion + QSS oscuro propio | Más estable y predecible que QML. No necesita librerías de temas externas. |
| Cálculos físicos | Internamente todo en **mm (Decimal)**. Conversión a pt y px en un solo módulo (`units.py`) | Una sola fuente de verdad. Evita errores de redondeo entre cm, pulgadas, puntos y píxeles. |
| Planificación vs. ejecución | `layout.plan(spec, imagen, modo, recorte) → RenderPlan` es una **función pura** | La vista previa y el PDF usan exactamente el mismo plan: lo que ves es lo que se imprime. Además es trivial de probar. |
| Procesamiento | Cola persistente en SQLite + `ProcessPoolExecutor` (1–2 procesos) | Si una imagen corrupta revienta, muere el proceso hijo y no la app. El progreso queda guardado después de cada imagen y se puede reanudar tras un fallo. |
| Motores IA | Interfaz `EnhancerEngine` + registro. Real-ESRGAN corre como **ejecutable externo** con sus modelos en `%LOCALAPPDATA%` | Se pueden actualizar binarios y modelos **sin reconstruir la app** (requisito §2). |
| PDF | **ReportLab** (BSD) para crear, **pypdf** (BSD) para verificar en las pruebas | Tamaño de página arbitrario y JPEG incrustado sin recomprimir. Evito PyMuPDF en el producto porque es **AGPL** (ver riesgos). |
| Credenciales | `keyring` → Administrador de credenciales de Windows | La API Key nunca toca un archivo de texto ni un log. |
| Instalación | PyInstaller en modo `--onedir` + instalador **Inno Setup** | Arranca más rápido que `--onefile` y genera menos falsos positivos de antivirus. |

### Estrategia de "paso directo" (calidad sin pérdida)
- **Modo Ajustar** con una imagen que no necesita remuestreo: el JPEG original se incrusta **byte a byte** en el PDF y los márgenes son simplemente la página. No hay recompresión.
- **Modo Recortar** con un JPEG: se incrusta el original y se recorta con una *máscara de recorte* del PDF, también sin recomprimir.
- Si hay remuestreo, mejora o fondo compuesto, la salida va **sin pérdida (Flate/PNG)** por defecto. La opción "JPEG 95 sin submuestreo de color" solo se ofrece para fuentes que ya eran JPEG.

### Política de resolución (separar PPI de imagen y DPI de impresora)
- `PPI efectivo = píxeles ÷ pulgadas físicas` en cada eje. Se usa el menor de los dos. Los 2400×1200 dpi de la Epson son gotas de tinta, no píxeles de imagen, y **nunca** se mezclan con este cálculo.
- El PPI de salida que elijas es un **tope**: si la imagen trae más, se reduce a ese valor (PDF más liviano). Si trae menos, **no se interpola por defecto**: se incrusta tal cual y el informe dice el PPI real.
- Solo se amplía si tú activas la mejora. El resultado se etiqueta como **"ampliado (IA local / interpolado)"** y nunca como "alta resolución original".

---

## 2. Estructura de carpetas

```
PrintMasterStudio/
├── pyproject.toml            # dependencias y config de pytest/ruff
├── README.md
├── PROGRESS.md               # registro de avances y pendientes (regla 12)
├── src/printmaster/
│   ├── __main__.py           # punto de entrada: python -m printmaster
│   ├── app.py                # crea QApplication, tema, ventana
│   ├── domain/
│   │   ├── units.py          # mm↔cm↔in↔pt↔px (Decimal)
│   │   ├── models.py         # PrintSpec, ImageItem, FitMode, CropAnchor, RenderPlan, JobStatus
│   │   └── quality.py        # umbrales de clasificación por perfil de uso
│   ├── core/
│   │   ├── image_loader.py   # lectura segura: EXIF, CMYK, 16 bits, rutas Unicode, miniaturas
│   │   ├── image_analyzer.py # nitidez, ruido, bloques JPEG, PPI efectivo, diagnóstico
│   │   ├── duplicates.py     # SHA-256 + hash perceptual (dHash)
│   │   ├── layout.py         # plan(): contain / fill / cover + posición del recorte
│   │   ├── composer.py       # ejecuta el RenderPlan (remuestreo Lanczos, fondo, alfa)
│   │   ├── color.py          # ICC embebido, conversión a sRGB, aplanado de transparencia
│   │   ├── pdf_writer.py     # un PDF por imagen, página exacta, PrintScaling=None
│   │   └── naming.py         # prefijo, numeración, carpetas por fecha/cliente
│   ├── engines/
│   │   ├── base.py           # EnhancerEngine (Protocol), capacidades, registro
│   │   ├── conservative.py   # interpolación + denoise no generativo (OpenCV)
│   │   ├── realesrgan.py     # wrapper del ejecutable ncnn-vulkan + respaldo CPU
│   │   ├── gemini.py         # cliente google-genai
│   │   └── budget.py         # cuotas, gasto mensual, contador de solicitudes
│   ├── printers/
│   │   ├── profiles.py       # PrinterProfile + validación de tamaño
│   │   └── epson_sc_t3170.json
│   ├── app_services/
│   │   ├── job_controller.py
│   │   ├── batch_runner.py   # cola persistente, pausa/reanudar/cancelar/reintentar
│   │   └── history.py
│   ├── infra/
│   │   ├── db.py             # SQLite + migraciones numeradas
│   │   ├── settings.py       # pydantic, %APPDATA%\PrintMasterStudio\settings.json
│   │   ├── secrets.py        # keyring
│   │   ├── paths.py          # appdata, caché, temporales
│   │   └── logging_setup.py  # log rotativo con filtro que oculta claves
│   └── ui/
│       ├── main_window.py    # barra lateral + páginas apiladas
│       ├── theme.qss
│       ├── pages/            # home, job, history, settings, ai_services
│       ├── widgets/          # queue_view, preview_canvas, inspector, before_after…
│       └── models/           # QAbstractListModel de la cola, miniaturas diferidas
├── tests/
│   ├── unit/  integration/  ui/  fixtures/ (imágenes sintéticas generadas en conftest)
├── tools/
│   ├── fetch_engines.py      # descarga y verifica (SHA-256) Real-ESRGAN y sus modelos
│   └── build_windows.ps1     # PyInstaller + Inno Setup
└── installer/printmaster.iss
```

**Rutas en el PC del usuario:** configuración en `%APPDATA%\PrintMasterStudio\`. Base de datos, caché, motores y logs en `%LOCALAPPDATA%\PrintMasterStudio\`. Los PDF van a la carpeta que elijas (por defecto `Documentos\PrintMaster\AAAA-MM-DD\Cliente\`).

---

## 3. Dependencias

| Paquete | Uso | Licencia |
|---|---|---|
| Python 3.12 (x64) | base | PSF |
| PySide6 | interfaz | LGPL-3 (OK con enlace dinámico; `--onedir` lo respeta) |
| Pillow | E/S de imágenes, ICC, Lanczos | MIT-CMU |
| opencv-python-headless | análisis, denoise, detección de rostros/texto | Apache-2 |
| numpy | cálculo | BSD |
| reportlab | escritura de PDF | BSD |
| pydantic v2 | validación de configuración | MIT |
| keyring | credenciales en Windows | MIT |
| google-genai | Gemini (SDK oficial actual; **no** el antiguo `google-generativeai`) | Apache-2 |
| onnxruntime | respaldo CPU para la ampliación (fase 3) | MIT |
| **Externo:** realesrgan-ncnn-vulkan + modelos | ampliación con GPU | MIT / BSD-3 |
| **Desarrollo:** pytest, pytest-qt, hypothesis, pypdf, ruff, pyinstaller | pruebas y build | — |

**Descartados a propósito:** PyMuPDF y Upscayl (ambos **AGPL**: obligarían a publicar el código si vendes la app). Tampoco uso pyvips por ahora; lo agrego solo si las pruebas de memoria lo exigen.

---

## 4. Diseño inicial de la interfaz

La barra lateral tiene las 7 secciones. **Nuevo trabajo, Procesamiento y Vista previa son tres pasos de una misma pantalla** (con un indicador de pasos arriba), para no perder el contexto al saltar entre páginas.

```
┌────┬────────────────────────────────────────────────────────────────┐
│ ⌂  │  ① Cargar ─── ② Formato ─── ③ Revisar ─── ④ Exportar            │
│ ＋ ├──────────────┬────────────────────────────────┬────────────────┤
│ ⚙︎ │ COLA (48)    │                                 │ FORMATO         │
│ 👁 │ ▣ img_01 ●Exc│     ┌─────────────────────┐     │ Ancho [60 ] cm▾ │
│ 🕘 │ ▣ img_02 ●Ace│     │  página 60×90 cm    │     │ Largo [90 ]     │
│ 🔧 │ ▣ img_03 ▲Baj│     │  ░░ zona recortada  │     │ ⟳ Auto ○ Vert   │
│ ✦  │ ▣ img_04 ✕Err│     │  [imagen]           │     │ ★ Favoritos ▾   │
│    │  …           │     └─────────────────────┘     │ PPI [200 ▾]     │
│    │ [+ Archivos] │  zoom − ▭ +   ⇆ antes/después   │ Modo: Ajustar ▾ │
│    │ [+ Carpeta]  │                                 │ IA: ◯ apagada   │
│    │ arrastre aquí│  PPI efectivo 143 · Aceptable   │ DIAGNÓSTICO …   │
├────┴──────────────┴────────────────────────────────┴────────────────┤
│ ████████░░░░ 31/48   ⏸ Pausar  ✕ Cancelar      [Aprobar todo] [Exportar PDF] │
└──────────────────────────────────────────────────────────────────────┘
```

- **Cola:** miniaturas cargadas en segundo plano (modo *draft* de JPEG, así que es casi instantáneo). Se reordena arrastrando y se quitan elementos con Supr. Muestra un indicador de estado, un aviso de duplicado y, al pasar el cursor, tamaño, dimensiones y formato.
- **Lienzo:** QGraphicsView con la página a escala real, márgenes físicos de la impresora en línea discontinua y la zona que se recorta sombreada. **El recorte se arrastra con el mouse.**
- **Inspector:** los cambios se aplican a la imagen seleccionada o a "todas las seleccionadas". Cambiar un parámetro solo recalcula el `RenderPlan`, no reprocesa todo.
- **Historial:** tabla filtrable con el botón "Regenerar PDF con estos parámetros".
- **IA y servicios:** estado de la GPU, motores instalados, API Key de Gemini, gasto del mes contra el límite.
- Interfaz en español, botones grandes, tema oscuro y diseño que se adapta con *splitters* desde 1366×768.

---

## 5. Flujo de procesamiento

```
Cargar ─► Diagnóstico ─► Recomendación ─► [ajustes del usuario] ─► Plan ─► (Mejora) ─► Composición ─► Color ─► PDF ─► Historial
 metadatos   proxy 2048px    reglas        recalcula solo el plan    puro    caché       final px     sRGB    1/imagen
```

1. **Carga:** solo metadatos y miniatura. El original **nunca** se modifica ni se mueve. Se corrige la orientación EXIF, se detectan CMYK, 16 bits, transparencia y WEBP animado (se toma el primer cuadro). Se registran el hash SHA-256 y el dHash.
2. **Diagnóstico** (sobre una copia reducida, en segundo plano):
   - nitidez: varianza del Laplaciano normalizada por tamaño;
   - ruido: estimador de Immerkær;
   - bloques JPEG: discontinuidad en bordes de 8×8 más la calidad estimada desde las tablas de cuantización;
   - PPI efectivo para el formato elegido.
3. **Clasificación** (umbrales editables, perfil "Póster/visión a >1 m" por defecto):
   Excelente ≥ 250 · Buena 180–249 · Aceptable 120–179 · Baja 72–119 · Muy baja < 72 PPI.
   Si la nitidez o el ruido salen mal, la categoría baja un nivel y se explica por qué.
4. **Recomendación:** conservar / ampliar ×2 o ×4 / reducir ruido / revisar manualmente. Indica el motor sugerido, la resolución que se alcanzaría y el resultado esperado en palabras ("mejora bordes; no recupera detalle perdido").
5. **Plan:** `RenderPlan` con página en mm y pt, rectángulo destino, recorte, px finales y fondo. La vista previa lo dibuja tal cual.
6. **Mejora (opcional):** el resultado se guarda en caché por `hash + motor + parámetros`, así que cambiar el formato después no obliga a repetir la IA.
7. **Composición:** Lanczos solo cuando es necesario. Fondo blanco, de color, color tomado de los bordes o extensión difuminada.
8. **Color:** se conserva el ICC embebido. Si no lo hay, se asume sRGB. CMYK se convierte a sRGB con su perfil. **No se convierte a CMYK**: el driver Epson espera RGB y hace su propia gestión de color. La transparencia se aplana a blanco por defecto (el plotter no imprime blanco) y existe la opción de conservarla.
9. **PDF:** página = mm × 72 / 25,4 pt exactos, sin márgenes añadidos, `/PrintScaling /None` en las preferencias del visor y metadatos con tamaño, PPI y motor usados.
10. **Historial:** registro con todos los parámetros en JSON, para poder regenerar el PDF.

**Aprobación:** cada imagen pasa por los estados Pendiente → Analizada → Lista → **Aprobada** → Exportada (o Error, con reintento). "Aprobar todo" aprueba solo las que no tienen advertencias críticas; las demás piden confirmación individual.

---

## 6. Estrategia de integración de Gemini

- **SDK oficial `google-genai`.** El modelo es configurable y la lista se obtiene de la API (no queda fijo en el código, porque Google cambia los modelos con frecuencia; por ejemplo, ya anunció el retiro de `gemini-2.5-flash-image`). Por defecto propongo el modelo Flash de imagen más reciente como opción económica y el Pro como opción de calidad.
- **Datos verificados (oct 2026, ai.google.dev):** la salida máxima es **4096×4096 px (4K)**, y el 4K cuesta alrededor de **US$0,24 por imagen** en el modelo Pro. Los modelos Flash van aproximadamente de US$0,045 a US$0,067 por imagen en 512 px–1K.
  → **Consecuencia de diseño:** 60×90 cm a 200 PPI necesita 4724×7087 px, más de lo que entrega Gemini. Por eso Gemini se usa para **restaurar** (a ≤ 4K) y luego el motor local o Lanczos lleva la imagen al tamaño final. Gemini nunca es el paso final.
- **Consentimiento:** un diálogo por trabajo muestra cuántas imágenes se enviarán, el costo estimado y la advertencia de que se envían a Google. La casilla "recordar para este trabajo" **no** queda guardada de forma global.
- **Control de gasto:** se lleva un registro en SQLite de cada llamada (tokens de `usage_metadata` × tabla de precios editable). Hay límite mensual en USD, máximo de solicitudes por día y por trabajo, y un **corte duro** antes de superar el límite. La API no devuelve el costo directamente; es una estimación y así se rotula.
- **Modo conservador obligatorio:** si se detectan texto, rostros o logos (OpenCV: detector de texto y YuNet para rostros), Gemini queda desactivado para esa imagen salvo que lo actives manualmente con una advertencia explícita. El *prompt* siempre pide preservar la composición, el texto y los colores, pero **no se confía en el prompt**: la vista antes/después es obligatoria antes de aprobar.
- **Privacidad:** la API Key se guarda en el Administrador de credenciales de Windows y nunca en logs. Recomiendo usar una clave del **nivel de pago**, porque los términos de Google permiten usar el contenido del nivel gratuito para mejorar sus productos (lo verifico antes de la fase 4). Una suscripción Google AI Plus/Pro **no** incluye cuota de API.
- **Fallos:** reintento con espera creciente ante 429/5xx, tiempo de espera por solicitud, y si Gemini falla la imagen sigue por el flujo local. La app funciona igual sin Gemini.

---

## 7. Estrategia de ampliación local

- **Motor principal:** `realesrgan-ncnn-vulkan` como ejecutable externo (MIT). Usa **Vulkan**, así que sirve en GPU NVIDIA, AMD **e Intel integradas**. Se ejecuta como subproceso, aislado de la app, y se puede cancelar.
- **Modelos según el tipo de imagen:**
  - `realesrgan-x4plus` para fotos;
  - `realesr-general-x4v3` para fotos con ruido (fuerza de denoise ajustable);
  - `realesrgan-x4plus-anime` para ilustraciones y gráficos planos.
  La elección es automática según el diagnóstico, con posibilidad de cambiarla.
- **Ampliar solo lo necesario:** el factor (×2 o ×4) se elige para alcanzar el PPI objetivo y luego se reduce con Lanczos al tamaño exacto. Se procesa en **tiles** para limitar la VRAM, porque un ×4 de 3000×4000 serían 192 MP.
- **Detección de GPU:** al iniciar, `realesrgan-ncnn-vulkan` lista los dispositivos. Si no hay Vulkan, se usa el **respaldo CPU con onnxruntime**, con la advertencia "≈10–30× más lento". El tiempo se estima con una imagen de prueba la primera vez.
- **Motor conservador (siempre disponible, sin IA):** Lanczos más un *unsharp* suave y denoise no local de OpenCV. Es la opción por defecto para imágenes con texto o logos.
- **Instalación de motores:** `tools/fetch_engines.py` o el botón "Instalar motor" descargan desde los *releases* oficiales y verifican el SHA-256. También pueden ir incluidos en el instalador como componente opcional.

---

## 8. Riesgos técnicos

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Ancho físico:** la SC-T3170 acepta rollos de 329 a 610 mm y hojas de 210 a 610 mm, con márgenes laterales de 3 mm. Un ancho de 60 cm cabe (área útil ≈ 603,6 mm), pero queda muy justo. | El perfil valida el lado menor ≤ 610 mm y rota automáticamente si el otro lado cabe. Si ambos lados superan 610 mm, se bloquea con un mensaje ("requiere otra impresora o dividir en paneles"). Si el diseño invade los 3 mm de margen físico, se muestra una advertencia. |
| R2 | **Precisión:** Epson indica ±0,1 % en precisión de línea (≈ ±0,6 mm en 60 cm). | El PDF es exacto. La desviación de la máquina se documenta y se ofrece una "hoja de calibración" opcional en la fase 5. |
| R3 | **Impresión escalada** por Acrobat o el driver ("Ajustar a página"). | `/PrintScaling /None`, una guía en el README e indicaciones en la pantalla de exportación. |
| R4 | Las **rutas con tildes o ñ** rompen `cv2.imread` en Windows. | Toda la lectura pasa por `image_loader` (Pillow / `np.fromfile` + `cv2.imdecode`). Hay prueba dedicada. |
| R5 | **Memoria:** 60×150 cm a 300 PPI son ≈ 7087×17717 px, unos 377 MB en RGB. | Un solo original en RAM por proceso, como máximo 2 procesos. Miniaturas en *draft*. Tiles en la IA. Prueba de pico de memoria. Si no alcanza, se agrega pyvips. |
| R6 | **Imágenes problemáticas:** CMYK sin perfil, 16 bits, EXIF girado, archivos corruptos, "bombas" de descompresión. | Normalización en el loader. Límite de píxeles configurable. Cada imagen corre aislada en un proceso hijo. Hay *fixtures* para cada caso. |
| R7 | **Cambios de color** inesperados. | Se conserva el ICC y no se convierte a CMYK. Prueba de que el ICC llega al PDF. |
| R8 | La **IA generativa altera** textos o logos. | Modo conservador por defecto, detección de texto y rostros, antes/después obligatorio y Gemini nunca automático. |
| R9 | **Licencias** (AGPL de PyMuPDF/Upscayl, LGPL de Qt). | Excluidas desde el diseño. Distribución `--onedir`. Archivo `LICENSES/` en el instalador. |
| R10 | **SmartScreen/antivirus** marcan un .exe sin firmar. | `--onedir` + Inno Setup. Como el uso es propio (D1), basta con "Más información → Ejecutar de todas formas" la primera vez. El certificado solo hace falta si algún día se vende. |
| R11 | **Gemini** cambia modelos, precios o límites. | Modelo y precios configurables, lista obtenida de la API, módulo aislado. |
| R12 | Yo trabajo en un contenedor **Linux**, no en Windows. | El núcleo y las pruebas corren aquí. El build y las pruebas de UI en Windows corren en **GitHub Actions `windows-latest`** y la validación final la haces en tu PC con un checklist. No declararé nada "listo para producción" sin esa prueba (regla 15). |
| R13 | Tamaño de página **> 5080 mm** (límite clásico de Acrobat, 200"). | Validación con aviso. No afecta los formatos actuales. |

---

## 9. Plan de pruebas

**Unitarias (pytest + hypothesis):**
- `units`: ida y vuelta mm↔cm↔in↔pt↔px. Propiedad: 600 mm → 1700,787 pt ±0,01.
- `layout`: con miles de combinaciones aleatorias, el rectángulo destino nunca sale de la página en *contain*, siempre la cubre en *cover* y la relación de aspecto se conserva (±1 px).
- `analyzer`: imágenes sintéticas con desenfoque gaussiano conocido → la nitidez baja de forma monótona. Con ruido σ conocido, el estimador queda dentro de ±20 %. Con JPEG de calidad 30 se detectan bloques.
- `quality`: límites exactos de cada categoría.
- `profiles`: 61 × 90 cm → advertencia/rotación; 70 × 70 cm → bloqueo.

**Integración (PDF, el corazón del producto):**
- Para cada formato (60×45, 60×90, 60×120, 50×70, 40×60, 60×150, en cm, mm y pulgadas), `pypdf` lee el **MediaBox** y verifica que coincide con mm × 72/25,4 ±0,01 pt. Además: una sola página, sin márgenes añadidos y con PrintScaling=None.
- **Sin recompresión:** en modo paso directo, el stream DCT incrustado es **idéntico byte a byte** al JPEG original.
- Fuentes PNG/TIFF: el stream es Flate (sin pérdida), los píxeles decodificados son iguales a la imagen compuesta, el ICC está presente y la transparencia se aplana o conserva según la opción.
- Lote de 100 imágenes con 3 corruptas: 97 PDF generados, 3 errores registrados, la app no se cae y el reintento funciona.
- Reanudación: se mata el proceso a mitad del lote y al reabrir continúa sin duplicar.
- Memoria: el pico en una imagen de 60×150 a 300 PPI queda por debajo del umbral definido (psutil).
- Motores: Real-ESRGAN con un binario falso (contrato de argumentos y códigos de salida) y una prueba real marcada `@gpu`. Gemini con transporte simulado (cuotas, corte de gasto, 429, que la clave no aparezca en los logs) y una prueba real opcional marcada `@live`.

**UI (pytest-qt):** arrastrar y soltar, reordenar, cambiar el formato recalcula la vista previa, y una prueba que recorre **todos los botones** para comprobar que ninguno está sin conectar (regla 3).

**Aceptación en Windows (checklist manual):** instalar en un PC limpio (o en Windows Sandbox) sin Python, procesar 50 imágenes reales tuyas, abrir los PDF en Acrobat y verificar el tamaño, imprimir 2 piezas y medirlas con regla.

---

## 10. Orden exacto de implementación

**Fase 1 — aplicación funcional básica**
1. Esqueleto del proyecto: `pyproject`, ruff, pytest, CI de GitHub Actions (Linux y Windows), `PROGRESS.md`.
2. *Spike* de PDF: confirmar que ReportLab incrusta JPEG sin recomprimir, maneja la máscara de recorte y respeta PrintScaling. Si algo falla, el plan B es pikepdf (MPL). Pruebas primero.
3. `domain/units.py` y `models.py` con sus pruebas.
4. `printers/profiles.py` y el perfil de la SC-T3170, con pruebas.
5. `core/image_loader.py` (EXIF, CMYK, 16 bits, Unicode, miniaturas) con fixtures.
6. `core/layout.py` (contain/fill/cover + posición del recorte) con pruebas de propiedades.
7. `core/color.py` y `core/composer.py`.
8. `core/pdf_writer.py` y `naming.py`, más las **pruebas de dimensiones físicas**.
9. `core/image_analyzer.py` y `quality.py` (diagnóstico básico y PPI efectivo).
10. `infra/settings.py`, `paths.py` y `logging_setup.py`.
11. UI: ventana, tema, barra lateral, cola con miniaturas y arrastre, inspector de formato (unidades, favoritos, validación), lienzo de vista previa con recorte arrastrable, y exportación de la imagen seleccionada o de todas.
12. Prueba de punta a punta en Windows con imágenes reales → **entrega de la Fase 1 para tu revisión.**

**Fase 2:** 13. SQLite y migraciones → 14. `batch_runner` con pool de procesos, pausa/reanudar/cancelar/reintentar y persistencia → 15. progreso individual y general → 16. historial y regeneración → 17. duplicados → 18. registro de errores visible → 19. pruebas de memoria y optimización.

**Fase 3:** 20. interfaz `EnhancerEngine` y motor conservador → 21. instalador de motores → 22. wrapper de Real-ESRGAN con tiles, cancelación y detección de GPU → 23. respaldo con onnxruntime → 24. caché de mejoras → 25. vista antes/después → 26. diagnóstico avanzado (texto, rostros, recomendación de modelo).

**Fase 4:** 27. `secrets.py` (keyring) → 28. `gemini.py` con transporte simulado → 29. `budget.py` (registro de gasto, cortes) → 30. diálogo de consentimiento → 31. página de servicios de IA → 32. prueba real opcional.

**Fase 5:** 33. script de PyInstaller `--onedir` → 34. Inno Setup (accesos directos, desinstalador, motores opcionales) → 35. pruebas en PC limpio y en un segundo PC → 36. hoja de calibración opcional → 37. README de instalación y manual de usuario → 38. solo entonces, la declaración "lista para producción".

Al final de cada fase: pruebas en verde, `PROGRESS.md` actualizado y tu aprobación antes de pasar a la siguiente.
