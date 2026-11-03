# Fase 2C — Gemini en menos pasos y estilo morado — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mejorar con Gemini en un clic: se copia la imagen, se pega en Gemini y la app recibe el resultado sola (Descargas o Ctrl+V). Aplicar además el estilo morado de la referencia.
**Spec:** `docs/superpowers/specs/2026-11-02-fase2c-gemini-rapido-estilo-design.md`
**Architecture:** `DownloadWatch` (sin Qt, sondeo con reloj inyectable) + cambios en `JobPage`/`QualityPanel`/`SettingsPage` + `ui/icons.py` y QSS nuevo.

## Global Constraints
- No se automatiza la app de Gemini y no hay llamadas de red a Gemini.
- Acento `#7c5cff` y el resto de la paleta, exactamente como en la §2 de la especificación.
- Lado mayor máximo de la imagen copiada: 3072 px. Sondeo cada 1 s. La espera expira a los 900 s. Un solo pedido pendiente.
- Nada se mueve ni se modifica en Descargas.
- Todos los textos, exactos de la especificación.

## Review Focus
1. **Descarga a medias** (`.crdownload` o tamaño que sigue creciendo): no se adjunta hasta que el archivo esté completo. → T1.
2. **Descargas no relacionadas** mientras se espera: solo cuentan los archivos posteriores al clic. → T1.
3. **El usuario cambia la selección mientras espera:** se adjunta a la imagen que estaba en espera. → T3.
4. **Ctrl+V dentro de un campo de texto:** pega en el campo y no dispara el pegado de la imagen. → T3.
5. **Carpeta de Descargas inexistente o mal configurada:** no se cae y avisa. → T1/T3.

### Task 1: `DownloadWatch` y la configuración
- Crear `src/printmaster/core/enhance/download_watch.py`:
  - `DownloadWatch(folder: Path, since: float, exts=SUPPORTED_EXTENSIONS)`;
  - `poll() -> Path | None` (estabilidad en dos sondeos);
  - `folder_ok: bool`.
- Settings:
  - `gemini_open_mode: Literal["desktop","web"] = "desktop"`;
  - `gemini_url: str = GEMINI_URL`;
  - `downloads_dir: Path = Path.home()/"Downloads"`.
- [ ] Pruebas `tests/unit/test_download_watch.py`, con las 4 de la §4 de la especificación más el caso de configuración.
- [ ] RED → GREEN → commit.

### Task 2: Iconos, tema morado, barra lateral, Inicio y tarjetas en Configuración
- `ui/assets/icons/*.svg` con los 12 de la especificación; `ui/icons.py: icon(name, color="#ece9f5", size=20) -> QIcon`.
- `theme.qss` reescrito con la paleta; `apply_dark_theme` actualiza la `QPalette`.
- `MainWindow`: encabezado de marca (`brand_label`) sobre el nav y un icono por elemento.
- `HomePage`: saludo, botón-tarjeta y favoritos como `QPushButton` en un layout de flujo (`favorite_buttons`), conservando la señal `favorite_chosen`.
- `SettingsPage`: los `QGroupBox` pasan a `QFrame#card` con un título interno.
- [ ] Pruebas `tests/ui/test_style_2c.py`:
  - existen los íconos;
  - `icon()` no es nulo;
  - los elementos del nav tienen ícono;
  - `brand_label.text()` contiene "PrintMaster";
  - el QSS contiene `#7c5cff`;
  - hay un botón por favorito y su clic emite `favorite_chosen`.
  - Ajustar `test_main_window.py` si cambia algo.
- [ ] RED → GREEN → commit.

### Task 3: Flujo Gemini v2 en la página de trabajo
- `QualityPanel`:
  - `paste_btn` ("Pegar mejorada (Ctrl+V)", reemplaza el texto de la zona; la zona sigue aceptando arrastrar y clic);
  - `copy_prompt_btn` (visible si `gemini_url` no contiene "/gem/");
  - `stop_wait_btn` ("Dejar de esperar");
  - `wait_label`.
- `JobPage`:
  - `_on_gemini()`: copia la imagen escalada a ≤3072 al portapapeles y guarda `self._copied_digest` (hash de los píxeles); abre la URL solo en modo web; crea `self._waiting = (item, DownloadWatch(...))` y arranca `self._watch_timer` (1000 ms).
  - `_poll_downloads()`: si encuentra un archivo, llama a `_on_external_dropped(path, target=item)`; si pasaron 900 s, muestra el mensaje de expiración.
  - `_paste_from_clipboard()`: atajo `QShortcut(QKeySequence.Paste, self, context=Qt.WidgetWithChildrenShortcut)`. Ignora el pegado si el foco está en un `QLineEdit`, `QAbstractSpinBox` o `QPlainTextEdit` (en ese caso pega en el campo). Contempla los avisos de la imagen original y del portapapeles vacío.
  - `_on_external_dropped(path, target=None)`: si se pasa `target`, se adjunta a ese ítem, no al seleccionado.
  - Se elimina la llamada a `_reveal` del flujo de Gemini.
- [ ] Pruebas `tests/ui/test_gemini_2c.py`: las de la §4 de la especificación (portapapeles, modos, vigilancia de punta a punta con `page._poll_downloads()` llamado a mano, Ctrl+V en sus 3 casos y Ctrl+V con el foco en un spinbox). Ajustar `test_job_page_2b.py` (ya no hay `revealed`).
- [ ] RED → GREEN → commit.

### Task 4: Sección Gemini en Configuración
- `gemini_open_combo` ("Solo copiar (uso la app de escritorio, Alt+Espacio)" / "Abrir Gemini en el navegador"), `gemini_url_edit`, guía del Gem, `copy_instructions_btn`, `downloads_edit` + `change_downloads_btn`.
- [ ] Pruebas en `tests/ui/test_settings_page_fase2a.py`: guardar el modo, la URL y Descargas; `copy_instructions_btn` copia el prompt.
- [ ] RED → GREEN → commit.

### Task 5: Verificación y entrega
- [ ] Capturas offscreen (Inicio, trabajo con imágenes, en espera de Gemini, Configuración) a 1366×697. Revisarlas y corregir.
- [ ] README, aceptación (sección 2C) y PROGRESS.
- [ ] CI verde en Windows y Linux, revisión independiente, corrección de hallazgos y merge a `main` (Camilo ya pidió usarla).
