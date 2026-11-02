# Fase 2A — Lámina de 60 cm con largo automático, precio sugerido y mejora local con IA

**Estado:** propuesta para aprobación · **Fecha:** 2 nov 2026
**Origen:** primera prueba real de Camilo con la Fase 1, sobre imágenes de 554×554 px y 236×420 px impresas en 60×90 cm.
**Se agrega a:** `2026-11-02-printmaster-studio-design.md`. Lo que no se menciona aquí sigue igual. Esta fase se hace **antes** que la Fase 2 original (lotes en segundo plano e historial).

## 0. Lo que se pidió

1. La plotter imprime en un rollo de 60 cm de ancho, así que **el ancho por defecto es 60 cm** y lo que cambia es el largo. Junto a cada imagen debe aparecer el **precio sugerido**: 60×45 vale $10.000 y 60×90 vale $15.000; los demás largos salen por equivalencia.
2. Las imágenes de baja calidad se tienen que **mejorar** para que la impresión quede bonita.
3. La imagen debe salir **completa, sin recortes y sin espacio sobrante**: el largo de la lámina se ajusta a la imagen, de forma manual o automática, y se muestra el precio de ese largo.

**Decisiones de Camilo:**
- Precio redondeado al **$1.000 más cercano**.
- Largo automático redondeado **hacia arriba de 5 en 5 cm**.
- **Precio mínimo de $10.000.**
- Motor de mejora: **local ahora (Real-ESRGAN)** y Gemini después (Fase 4).

## 1. Lámina de ancho fijo y largo automático

- La configuración gana el campo `roll_width_mm`, con valor por defecto **600**. Es el ancho por defecto de todo formato nuevo.
- **Modo nuevo y predeterminado: "Ajustar largo a la imagen"** (`FitMode.FIT_LENGTH`).
  - El ancho de la página es `roll_width_mm`.
  - Largo exacto = `ancho × alto_px / ancho_px`.
  - Largo de la lámina = el exacto **redondeado hacia arriba al múltiplo de 50 mm**, con un mínimo de 50 mm.
  - La imagen ocupa todo el ancho y se centra en el largo. El sobrante es siempre menor de 5 cm y se reparte arriba y abajo en blanco. Nunca se recorta.
  - El largo calculado se muestra en el inspector como solo lectura, con la nota "calculado".
- Ejemplos (verificados con el cálculo):

  | Imagen | Largo exacto | Lámina | Precio |
  |---|---|---|---|
  | 554×554 | 60,0 cm | 60×60 | $12.000 |
  | 236×420 | 106,8 cm | 60×110 | $17.000 |
  | 4000×3000 (horizontal) | 45,0 cm | 60×45 | $10.000 |
  | 3000×4500 | 90,0 cm | 60×90 | $15.000 |
  | 1000×3000 | 180,0 cm | 60×180 | $25.000 |
  | 3000×1000 (panorámica) | 20,0 cm | 60×20 | $10.000 (mínimo) |

- **Los modos manuales se mantienen** (Ajustar sin recortar, Rellenar y Recortar). El ancho por defecto pasa a ser 60 cm y el largo se escribe a mano.
- **Orientación:** el valor por defecto pasa a ser **"Como se escribió"** (`Orientation.AS_ENTERED`). El ancho es siempre el lado que cruza el rollo y la página **nunca** se gira por su cuenta. Esto resuelve el hallazgo R1 pendiente de la Fase 1: con 60 de ancho siempre cabe y no hace falta rotar al imprimir. Las opciones Automática, Vertical y Horizontal siguen disponibles para casos especiales.
- Los favoritos por defecto pasan a ser largos con ancho 60: `60×30, 60×45, 60×60, 60×90, 60×120, 60×150`. Los favoritos que Camilo ya guardó no se tocan.

## 2. Precio sugerido

- Fórmula lineal que pasa por los dos precios de referencia, escalada por área para anchos distintos de 60:
  - `largo_equivalente = largo_mm × ancho_mm / 600`
  - `precio = 10.000 + (largo_equivalente − 450) × (15.000 − 10.000) / (900 − 450)`
  - luego se redondea al múltiplo de $1.000 más cercano (las mitades suben: $12.500 → $13.000);
  - por último se aplica el mínimo: `max(10.000, precio)`.
- Todo se configura en la sección "Precios" de Configuración: los dos puntos de referencia (largo y precio), el mínimo y el redondeo.
- Dónde se muestra:
  - en la tarjeta de diagnóstico ("Precio sugerido: $17.000");
  - en el tooltip de la cola;
  - en una etiqueta de **total del lote** en la barra inferior ("4 láminas · $54.000").
  - En el modo de largo automático cada imagen tiene su propio largo y su propio precio.
- Es un **precio sugerido**, solo informativo. No se guarda en el PDF ni se cobra nada.

## 3. Mejora local con IA (Real-ESRGAN)

### 3.1 Motor
- Se usa el ejecutable oficial `realesrgan-ncnn-vulkan` para Windows, del release v0.2.5.0 de xinntao/Real-ESRGAN (licencia BSD-3), con sus modelos `realesrgan-x4plus` (fotos) y `realesrgan-x4plus-anime` (ilustraciones, logos y textos planos).
- **Instalación:** botón "Instalar motor de mejora" en Configuración. Descarga el zip oficial de GitHub, lo descomprime en `%LOCALAPPDATA%\PrintMasterStudio\engines\realesrgan\` y verifica que el ejecutable responde. Así no se reconstruye la app (especificación §2) y el instalador no crece.
- **GPU:** usa Vulkan (NVIDIA, AMD o Intel integrada). Al instalar se hace una prueba con una imagen de 64×64 px. Si no hay Vulkan, se muestra "Su equipo no tiene aceleración compatible; se usará la mejora básica (más rápida, menos detalle)" y se usa el **motor conservador**: Lanczos más un enfoque suave, sin IA. El respaldo por CPU con onnxruntime queda para más adelante, solo si hiciera falta.

### 3.2 Cuándo y cómo se mejora
- Un interruptor general **"Mejorar imágenes de baja calidad"**, activado por defecto. Cada imagen puede quedar en Automático, Mejorar o No mejorar.
- En Automático se mejora cuando el nivel base del diagnóstico es BAJA o MUY_BAJA.
- **Objetivo: 150 PPI efectivos** (configurable).
  - Pasadas ×4 necesarias = la menor cantidad tal que `PPI_original × 4ⁿ ≥ objetivo`, con un **máximo de 2 pasadas** (×16).
  - Ejemplos: 236 px a 60 cm (10 PPI) → 2 pasadas, 3776 px, 160 PPI. 554 px a 60 cm (23 PPI) → 2 pasadas, 8864 px. Si el resultado supera el PPI de salida, el PDF lo reduce, como ya hace hoy.
- **Elección de modelo automática:** si la imagen tiene pocos colores distintos (menos de 4096 colores en el proxy cuantizado a 5 bits por canal) o mucha área plana, se usa `x4plus-anime`; si no, `x4plus`. Se puede cambiar por imagen.
- La mejora corre **en segundo plano, una imagen a la vez**. Se ve el estado "Mejorando… (pasada 1/2)" y se puede cancelar.
- El resultado se guarda como **PNG sin pérdida** en `%LOCALAPPDATA%\PrintMasterStudio\cache\enhanced\<sha256>_<modelo>_<pasadas>.png` y se reutiliza si se vuelve a cargar la misma imagen. El original nunca se toca.
- El cálculo del ajuste, la vista previa y el PDF usan la versión mejorada como fuente. El diagnóstico muestra "Original: 236×420 px (10 PPI) → Mejorada con IA: 3776×6720 px (160 PPI)". **Nunca dice "alta resolución original".**
- **Antes/después:** botón "Ver original / Ver mejorada" en el lienzo. Es obligatorio revisar antes de "Aprobar seleccionada": "Aprobar todo" aprueba las mejoradas, pero avisa cuántas se mejoraron con IA para que se revisen.

### 3.3 Límites honestos (se muestran en la app)
- Real-ESRGAN mejora bordes, letras y colores planos, y reduce el ruido y los bloques JPEG. **No recupera detalle que la imagen nunca tuvo.** En imágenes de menos de unos 300 px, las letras pequeñas pueden deformarse; por eso existe la vista antes/después.
- Por la especificación §7 (textos, logos y rostros) se mantiene la regla: **Real-ESRGAN no es generativo**, no inventa contenido nuevo. Gemini, que sí es generativo, sigue en la Fase 4, con consentimiento.

## 4. Riesgos nuevos

| # | Riesgo | Mitigación |
|---|---|---|
| A1 | El PC no tiene Vulkan (o el driver es viejo) | Prueba al instalar, mensaje claro y motor conservador como respaldo. |
| A2 | Memoria con ×16: una imagen de 2000 px quedaría en 32000 px | La segunda pasada solo se hace si la primera no llega al objetivo. Se limita a 12000 px en el lado mayor (se reduce después de cada pasada) y se usa `-t` (tile) del motor para limitar la VRAM. |
| A3 | Antivirus o SmartScreen bloquean el ejecutable descargado, o la descarga llega dañada | Se descarga de `https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip` y se verifica el SHA-256 `e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96` (publicado por un espejo en Hugging Face; se confirma contra el archivo real en la primera instalación del PC de Camilo). Si el hash no coincide, no se instala y se muestra el error con su texto. |
| A4 | Lentitud en GPU integrada (segundos a decenas de segundos por imagen) | Una imagen a la vez, con progreso y cancelación, y caché por hash. |
| A5 | El precio con banker's rounding de Python (`round`) | Se usa `Decimal` con `ROUND_HALF_UP`. Hay prueba con el caso $12.500 → $13.000. |

## 5. Pruebas clave

- **Largo automático:** todos los ejemplos de la tabla §1. Propiedad: la lámina tiene siempre ≥ largo exacto, < largo exacto + 50 mm y es múltiplo de 50; el ancho es siempre 600; el PDF tiene el MediaBox de 600 × lámina.
- **Precio:** 450 → 10.000, 900 → 15.000, 600 → 12.000, 1100 → 17.000, 200 → 10.000 (mínimo), ancho 300 × 900 → 10.000, empate exacto que redondea hacia arriba, y valores configurables.
- **Mejora:** el envoltorio del motor se prueba con un ejecutable **falso** (un script que escala ×4 con Pillow) para el contrato de argumentos, las pasadas, la caché, la cancelación y los errores. La detección de Vulkan se prueba con un falso que falla. Hay una prueba real marcada `@gpu`, que se corre a mano en el PC de Camilo.
- **Integración:** una imagen de 236×420 con el motor falso termina en una lámina de 60×110, un PDF de 600×1100 mm y una fuente mejorada de ≥150 PPI efectivos; el original queda intacto.
- **UI:** el modo predeterminado es "Ajustar largo a la imagen", el largo aparece como solo lectura, el precio se muestra por imagen y en total, el botón antes/después alterna la vista, y la prueba de "ningún botón sin función" sigue pasando.

## 6. Fuera de esta fase

Gemini (Fase 4), lotes con pool de procesos e historial (Fase 2 original), respaldo de mejora por CPU con onnxruntime y extensión de fondo con IA.
