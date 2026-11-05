# PrintMaster Studio

Prepara imágenes de clientes y genera **un PDF por imagen** con dimensiones físicas exactas,
optimizado para el plotter **Epson SureColor SC-T3170** (rollo de hasta 610 mm).

Estado: **Fase 1** (aplicación funcional básica). Ver `PROGRESS.md`.

## Qué hace

- Carga múltiple: arrastrar y soltar archivos o carpetas, `+ Archivos`, `+ Carpeta`. Admite JPG, PNG, WEBP, BMP y TIFF.
- Diagnóstico por imagen: PPI efectivo en el tamaño elegido, nitidez, ruido, compresión JPEG y clasificación de calidad.
- Cualquier tamaño en cm, mm o pulgadas, con favoritos, orientación automática o manual, y validación contra la SC-T3170.
- Tres modos: **Ajustar sin recortar**, **Rellenar** (blanco, color, color del borde o difuminado) y **Recortar** (con recorte arrastrable).
- Vista previa a escala que usa el mismo cálculo que el PDF.
- PDF exactos: página en puntos exactos, sin márgenes añadidos y `PrintScaling=None`. El JPEG va sin recomprimir cuando es posible, sin pérdida en los demás casos, y con el perfil ICC incrustado.
- **Lámina de 60 cm con largo automático**: la imagen sale completa, sin recortes ni sobrantes grandes. Muestra el **precio sugerido** por pieza y el total del lote.
- **Mejora con IA local** (Real-ESRGAN) para imágenes de baja calidad, con comparación antes/después. El motor se instala desde *Configuración*.
- Nunca modifica ni borra los archivos originales.

## Instalar y ejecutar (Windows, PowerShell)

```powershell
git clone https://github.com/soysebasst/PrintMasterStudio.git
cd PrintMasterStudio
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m printmaster
```

## Abrir con doble clic (acceso directo)

Después de instalar, haz **doble clic en `crear_acceso_directo.bat`** (en la carpeta del proyecto).
Crea **"PrintMaster Studio"** en el Escritorio y en el menú Inicio. Abre la app sin consola, usando
`.venv\Scripts\printmaster-studio.exe`.

## Mejorar con Gemini (gratis)

1. Selecciona la imagen y pulsa **«Mejorar en Gemini»**: la app copia **la imagen** al portapapeles.
   - Modo por defecto: no abre nada; abre la app de escritorio de Gemini con **Alt+Espacio**.
   - Modo navegador (Configuración › Gemini): abre la dirección de Gemini o de tu Gem.
2. En Gemini pega con **Ctrl+V** y envía. Si creaste un **Gem** con las instrucciones (Configuración › «Copiar instrucciones»), no hace falta pegar el prompt; si no, usa el enlace «Copiar prompt».
3. Trae el resultado de una de estas formas:
   - **Descárgalo**: la app vigila la carpeta de Descargas y lo adjunta sola a la imagen en espera (hasta 15 minutos).
   - **Cópialo** (clic derecho › Copiar imagen) y pulsa **Ctrl+V** en la app o «Pegar mejorada».
   - Arrástralo a la zona punteada.

La app conserva el largo y el precio del original. Descargar el resultado da la resolución completa; «Copiar imagen» de Gemini entrega una copia reducida (la app avisa).

## Largo y giro

- **Largo auto:** la lámina mide justo lo que mide la imagen a 60 cm de ancho (al milímetro), sin franjas blancas. El precio se cobra por tramos de 5 cm.
- **Escribir otro largo:** si cambias el largo, la imagen llena esa lámina (modo «Recortar») y arrastras la imagen para elegir qué parte se corta.
- **Girar 90°:** imprime la imagen girada dentro de la misma lámina (una horizontal de 90×60 sale girada en 60×90). Con tamaño fijo se gira sola cuando así llena mejor el papel; el botón lo cambia a mano.
- La **resolución** se ajusta solo en Configuración.

## Recortar a mano

Pulsa **Recortar** sobre la vista previa: arrastra las esquinas o los bordes para elegir qué parte se imprime y el centro para mover el marco (también con las flechas). Puedes dejar el marco libre o fijarlo a la proporción original o de un favorito (por ejemplo 60 × 90). En «Largo auto», el largo y el precio salen de la zona recortada y se ven en vivo.

## Desarrollo y pruebas

```powershell
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest -q        # todas las pruebas
.venv\Scripts\ruff check .     # estilo
```

En Linux/CI sin pantalla: `QT_QPA_PLATFORM=offscreen pytest -q`.

## Al imprimir

Abre el PDF en Acrobat y en el diálogo de impresión elige **"Tamaño real"**. El tipo de papel, la calidad y la gestión de color se ajustan en el controlador Epson.

## Ubicaciones

| Qué | Windows |
|---|---|
| PDF | `Documentos\PrintMaster\AAAA-MM-DD\` |
| Configuración | `%APPDATA%\PrintMasterStudio\settings.json` |
| Logs | `%LOCALAPPDATA%\PrintMasterStudio\logs\printmaster.log` |

## Estructura

```
src/printmaster/
  domain/        unidades, modelos, calidad (Python puro)
  printers/      perfiles de impresora (JSON) y validación
  core/          carga, ajuste, composición, color, PDF, nombres, diagnóstico
  infra/         rutas, configuración, logs
  app_services/  JobController (cola, aprobación, exportación)
  ui/            interfaz PySide6
tests/           unit/, integration/, ui/
docs/            especificación, planes y checklist de aceptación
```
