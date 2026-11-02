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
