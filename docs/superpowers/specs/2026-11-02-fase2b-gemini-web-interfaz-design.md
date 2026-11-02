# Fase 2B — Mejora con Gemini (web, gratis) e interfaz rediseñada

**Estado:** propuesta para aprobación · **Fecha:** 2 nov 2026
**Origen:** prueba de Camilo con la Fase 2A. Real-ESRGAN apenas cambia imágenes de ~236 px; Gemini web dio un resultado excelente y conservó el texto. La interfaz resulta incómoda: tiene demasiadas opciones a la vista y no es claro qué hacer después.
**Se agrega a:** `2026-11-02-printmaster-studio-design.md` y `2026-11-02-fase2a-largo-precio-mejora-design.md`.

## 0. Decisiones de Camilo

- **Gemini por la web, gratis (opción A)**, de forma semiautomática. Se deja lista la integración por API (opción B) para más adelante. Hecho verificado: la API de Gemini **no** tiene nivel gratuito para modelos de imagen (foro oficial de Google, ago 2026). No se implementa rotación de cuentas para evadir cuotas: va contra los términos de Google.
- Gemini se usa **solo con un botón por imagen**. Nunca se envía nada automáticamente.
- Distribución aprobada (maqueta del 2 nov):
  - cola en **tarjetas en cuadrícula**;
  - **tema oscuro más limpio**;
  - **selector de unidad visible**;
  - pasos arriba;
  - barra inferior con **"Siguiente:"**, total y "Exportar N PDF";
  - panel derecho corto: Tamaño, Ajuste, Calidad y **Opciones avanzadas** plegadas.

## 1. Mejora con Gemini web (flujo A)

**Botón "Mejorar en Gemini"**, en la sección Calidad del panel derecho, para la imagen seleccionada:
1. Copia al portapapeles el **prompt fijo** (configurable en Configuración):
   > Mejora esta imagen para impresión en gran formato. Redibújala en alta resolución, con bordes nítidos y colores limpios. Conserva exactamente la composición, los colores, los personajes y TODO el texto tal como está escrito, letra por letra. No agregues ni quites elementos.
2. Abre `https://gemini.google.com/app?hl=es` en el navegador predeterminado (`QDesktopServices.openUrl`).
3. Abre el Explorador con el archivo original **seleccionado** (`explorer /select,<ruta>` en Windows; en otros sistemas, la carpeta).
4. Muestra un aviso breve: "Prompt copiado. En Gemini: sube la imagen, pega con Ctrl+V y descarga el resultado. Luego suéltalo en «Suelta aquí la mejorada»."

**Zona "Suelta aquí la mejorada"** (debajo del botón). Acepta arrastrar un archivo o hacer clic para elegirlo.
- El archivo se valida con `probe` y se **copia** a `data_dir()/cache/external/<sha_original>_<sha_nueva>.png` (convertido a PNG sin pérdida). El archivo descargado no se toca.
- **Validación de proporción:** si la proporción de la mejorada se aleja más de un 3 % de la del original, aparece el aviso "La imagen mejorada tiene otra proporción (Gemini la recortó o extendió). Se ajustará sin deformarla." En modo largo automático se ajusta con el modo **Ajustar** dentro de la lámina del original, sin deformar.
- Se registra como fuente mejorada con `EnhanceResult(engine="Gemini (web)", model="gemini-web", passes=0)`.
- **El largo y el precio siguen calculándose con la proporción del original**, igual que en la Fase 2A.
- **Paso local posterior automático:** si el PPI efectivo de la versión de Gemini es menor que el objetivo (150), se amplía en el PC con Real-ESRGAN si está disponible, o con la mejora básica, y el resultado se etiqueta "Gemini (web) + Real-ESRGAN". Si ya alcanza, no se toca.
- Con "No mejorar" se vuelve al original. "Ver original / Ver mejorada" funciona igual.
- Etiquetas honestas: la tarjeta dice "Mejorada con Gemini"; el diagnóstico conserva las métricas del original más el PPI nuevo (regla de la Fase 2A).
- **Advertencia permanente** junto al botón: "Gemini redibuja la imagen: revise textos, logos y caras antes de aprobar."

**Opción B (preparada, no activa):** `core/enhance/gemini_api.py` define la interfaz `GeminiEnhancer.enhance(src, prompt) -> Path`. En esta fase **no se implementa la llamada**. Configuración muestra "Gemini por API: disponible en una versión futura (requiere API Key con facturación)". No se agrega ninguna dependencia.

## 2. Interfaz rediseñada (pantalla "Nuevo trabajo")

**Encabezado:** título y **pasos** Cargar → Revisar → Exportar, como chips que cambian de estado: hecho (verde con ✓), actual (azul), pendiente (gris).

**Columna izquierda: cola en tarjetas en cuadrícula.**
- `QListView` en modo `IconMode`, con un delegado que dibuja tarjetas de ~150×190 px:
  - miniatura de 136×100, ajustada sin deformar;
  - nombre en una línea, cortado con "…";
  - "60×110 · $17.000";
  - **chip de estado en palabras**, con prioridad: Error > PDF listo > Aprobada > Mejorando… > Mejorar (si necesita mejora o el nivel es bajo) > Lista.
  - La insignia de origen ("IA", "Gemini", "Básica") va en la esquina de la miniatura.
- Encabezado "N imágenes" y botón "+ Agregar" (menú: Archivos… / Carpeta…).
- Zona punteada "Arrastra imágenes aquí" cuando la cola está vacía; con elementos, se puede seguir soltando sobre la cuadrícula.
- **Menú contextual** (clic derecho): Quitar, Subir, Bajar, Abrir carpeta del archivo. Supr sigue funcionando. Se eliminan los botones grandes ▲ ▼ Quitar.
- Reordenar con arrastre interno (`moveRows`), más Subir/Bajar en el menú.

**Centro: vista previa.**
- Barra superior: conmutador segmentado **Original | Mejorada** (habilitado solo si hay mejora) y zoom en iconos −, ajustar, +.
- Debajo, en gris: "60 × 110 cm · 160 PPI efectivos".

**Columna derecha: panel corto** (sin desplazamiento a 1366×768).
1. **Tamaño:** Ancho, Largo (con "auto" en largo automático) y **Unidad visible**, más "$17.000 sugerido" en verde.
2. **Ajuste:** 4 botones conmutables en cuadrícula de 2×2: Largo auto · Ajustar · Rellenar · Recortar. Debajo, Fondo, solo en Rellenar.
3. **Calidad:** chip de color con el nivel y el PPI ("Muy baja · 10 PPI"). Debajo:
   - la recomendación en una línea;
   - **Mejorar en Gemini** y la zona para soltar la mejorada;
   - un combo pequeño "Mejora automática / Forzar mejora local / No mejorar";
   - el estado de la mejora en una línea.
   - El detalle técnico (nitidez, ruido, calidad JPEG, avisos) queda dentro de un `QToolButton` "Ver detalles" que lo despliega.
4. **Opciones avanzadas** (plegadas por defecto; el estado se recuerda en la configuración): orientación, resolución (PPI), exportar sin pérdida y guardar formato favorito.
5. Los favoritos se mantienen en un combo en Tamaño.

**Barra inferior:**
- A la izquierda, **"Siguiente: …"**, calculado así:
  - sin imágenes → "Arrastra o agrega las imágenes del cliente";
  - analizando → "Analizando imágenes…";
  - hay imágenes con calidad baja sin mejorar → "Mejora «nombre» con Gemini o apruébala tal cual";
  - hay listas sin aprobar → "Revisa la vista previa y pulsa Aprobar todo";
  - hay aprobadas → "Exporta los PDF";
  - todo exportado → "Listo. Abre la carpeta de salida".
- A la derecha: el total "N láminas · $X", la barra de progreso (visible solo durante una exportación o mejora), "Cancelar mejora" (solo durante una mejora), **Aprobar todo** y el botón primario **"Exportar N PDF"**, donde N es la cantidad exportable.

**Tema:** se mantiene el oscuro, pero con:
- menos bordes (bordes de 1 px de `#2c2e33` solo en los contenedores principales);
- más espacio (márgenes de 12 a 16 px);
- tipografía de 10 pt, con títulos de sección de 11 pt en semibold;
- un solo botón primario azul por vista;
- chips con fondo tenue y texto de su color;
- sin cajas `QGroupBox` con título incrustado, que se reemplazan por etiquetas de sección.

**Barra lateral:** igual (Inicio, Nuevo trabajo, Configuración), con iconos y un poco más angosta.

**Configuración:** se reorganiza en secciones, con el mismo contenido: Salida, Precios y lámina, Mejora (motor local y Gemini web: prompt editable) y Favoritos.

## 3. Fuera de alcance

Gemini por API (llamada real), historial, lotes en un proceso aparte, tema claro y vista de lista de la cola.

## 4. Pruebas clave

- **Flujo Gemini web.** El botón copia el prompt exacto al portapapeles y pide abrir la URL y el Explorador; esas llamadas se interceptan en la prueba. Al soltar un PNG de 2304×4096 sobre "respeto" (236×420):
  - la fuente impresa pasa a ser la de Gemini (con el paso local si hace falta);
  - la lámina sigue en 60×110 y el precio en $17.000;
  - aparece la etiqueta "Gemini";
  - el PDF sale de 600×1100 mm;
  - el original queda intacto.
- **Proporción distinta** (1024×1024 para un original de 236×420): aparece el aviso, la lámina sigue en 60×110 y la imagen se ajusta dentro sin deformarse (se verifica la proporción del rectángulo de destino).
- **Archivo inválido** soltado en la zona: mensaje de error y la mejora previa no cambia.
- **Interfaz:**
  - la cola usa tarjetas con nombre cortado y el chip de estado correcto en cada caso;
  - el menú contextual quita y reordena;
  - "Siguiente:" muestra el texto esperado en cada estado;
  - "Exportar N PDF" refleja la cantidad;
  - las Opciones avanzadas están plegadas por defecto y recuerdan su estado;
  - el panel derecho cabe sin desplazamiento a 1366×768;
  - `test_no_dead_buttons` sigue pasando;
  - las pruebas de flujo existentes se adaptan a los nuevos nombres de los controles.
- **Capturas offscreen** de cada estado para revisarlas antes de entregar.
