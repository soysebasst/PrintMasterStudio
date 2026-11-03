# Fase 2C — Gemini en menos pasos (app de escritorio, Gem, Descargas y Ctrl+V) y estilo visual morado

**Estado:** propuesta para aprobación · **Fecha:** 2 nov 2026
**Origen:** Camilo confirma que el acceso directo, la importación, la exportación y el ajuste funcionan. Gemini da resultados mucho mejores que la mejora automática, que además es lenta. Quiere evitar tantas pestañas del navegador y ventanas del Explorador, usar la app de escritorio de Gemini con su cuenta Pro y tener una interfaz menos sencilla, con una referencia visual (tema oscuro violáceo y acento morado).
**Se agrega a:** las especificaciones anteriores en `docs/superpowers/specs/`.

## 0. Hechos y decisiones

- Existe la app oficial de Gemini para Windows (10 sep 2026, `gemini.google/desktop`, se abre con Alt+Espacio). **No ofrece ninguna interfaz para que otro programa la controle.** No se automatiza su manejo (clics, teclas o lectura de la pantalla): sería frágil y va contra las condiciones de uso automatizado de Google. Lo totalmente automático solo es posible por la API de pago, que queda para una fase futura.
- Decisiones de Camilo:
  - recibir el resultado **vigilando Descargas y también con Ctrl+V**;
  - **acento morado** como la referencia;
  - **solo el estilo visual**, sin tarjetas de resumen nuevas ni cambios de distribución.

## 1. Gemini en menos pasos

**Configuración, sección "Gemini":**
- **Al pulsar «Mejorar en Gemini»** (`gemini_open_mode`):
  - `"desktop"` (por defecto): no abre nada; el usuario usa la app de escritorio con Alt+Espacio.
  - `"web"`: abre `gemini_url` en el navegador.
- `gemini_url`: por defecto, la URL de Gemini. Si Camilo crea un **Gem**, aquí pega su dirección.
- **Guía del Gem**, con texto fijo: "Cree una vez un Gem en Gemini (Gems › Nuevo Gem), pegue estas instrucciones y guárdelo. Así no tendrá que pegar el prompt en cada imagen." Debajo van el prompt editable (`gemini_prompt`, como ahora) y el botón **"Copiar instrucciones"**.
- `downloads_dir`: por defecto `~/Downloads`; botón "Cambiar…".

**Botón «Mejorar en Gemini» (panel Calidad):**
1. Copia **la imagen** al portapapeles: el original normalizado, con un lado mayor máximo de 3072 px (`QClipboard.setImage`).
2. En modo `"web"`, abre `gemini_url`. **Ya no abre el Explorador.**
3. Marca la imagen como **en espera de Gemini** y empieza a vigilar Descargas (§1.1).
4. Muestra en el panel: "Imagen copiada. En Gemini: Ctrl+V y enviar. Luego descargue el resultado o cópielo (clic derecho › Copiar imagen) y pulse Ctrl+V aquí." Si no hay un Gem configurado, agrega un enlace **"Copiar prompt"** para pegarlo a mano.

### 1.1 Vigilancia de Descargas (`core/enhance/download_watch.py`, sin Qt)
- `DownloadWatch(folder: Path, since: float, exts=SUPPORTED_EXTENSIONS)`, con el método `poll(now: float) -> Path | None`. Devuelve el **archivo de imagen más reciente** con `mtime ≥ since` cuyo tamaño se mantuvo igual en dos sondeos seguidos (descarga terminada). Ignora `*.crdownload`, `*.part`, `*.tmp` y los archivos de 0 bytes.
- La página sondea cada 1 s con un `QTimer`. Solo hay **un pedido pendiente a la vez**, el último botón pulsado. Expira a los 15 minutos ("Ya no se espera la descarga de Gemini.").
- Al detectar el archivo, llama a `attach_external` sobre **esa** imagen (por identidad, aunque la selección haya cambiado) y avisa: "Mejora recibida de Gemini para «nombre»". El archivo descargado no se toca.
- Junto al estado "Esperando descarga de Gemini…" hay un enlace **"Dejar de esperar"**.

### 1.2 Pegar con Ctrl+V
- Atajo **Ctrl+V** en la página "Nuevo trabajo", fuera de los campos de texto, y botón **"Pegar mejorada"** (la zona actual, que también acepta arrastrar y hacer clic para elegir).
- Desde el portapapeles se toma la **imagen**, o la primera URL de archivo local que sea imagen. Se guarda como PNG en `cache/external/clipboard_<timestamp>.png` y se llama a `attach_external` sobre la imagen seleccionada (o sobre la que está en espera de Gemini, si existe).
- Si el portapapeles todavía tiene **la misma imagen que copió la app** (mismo tamaño y mismo hash de píxeles), muestra "El portapapeles todavía tiene la imagen original. En Gemini use clic derecho › Copiar imagen sobre el resultado." y no hace nada.
- Si el portapapeles no tiene una imagen, muestra "No hay ninguna imagen en el portapapeles."

## 2. Estilo visual morado (misma distribución)

- **Paleta:**
  - fondo `#15131c`;
  - superficie 1 `#1d1a27`; superficie 2 `#252134`; borde `#2e2a3d`;
  - texto `#ece9f5`; texto secundario `#a29cb8`; texto tenue `#7d7794`;
  - **acento `#7c5cff`** (hover `#8f74ff`); acento suave `#b9a6ff`; fondo del acento `#2d2547`;
  - éxito `#7ee7a8`, aviso `#f0c15a` y error `#ff9aa8`, cada uno con su fondo oscuro.
- **Barra lateral:**
  - encabezado de marca: icono de la app de 32 px y "PrintMaster" en acento suave con "Studio" debajo en texto secundario;
  - elementos con **iconos SVG** (inicio, nuevo trabajo, configuración), 40 px de alto y selección redondeada de 10 px en superficie 2.
- **Iconos:** SVG propios de trazo simple en `ui/assets/icons/`. Se cargan con `QIcon` y se tiñen al color del texto con `ui/icons.py: icon(name, color) -> QIcon`. Lista: `home`, `photo-plus`, `settings`, `sparkles`, `clipboard`, `download`, `plus`, `zoom-in`, `zoom-out`, `maximize`, `check`, `x`.
- **Tarjetas y paneles:**
  - esquinas de 12 px;
  - la cola, la vista previa y el panel derecho van sobre superficie 1, con 12 px de separación entre paneles;
  - la tarjeta seleccionada lleva un borde de acento de 2 px.
- **Botones:**
  - "Mejorar en Gemini" y "Exportar N PDF" usan el acento sólido (son las dos acciones principales de pasos distintos);
  - los segmentos marcados usan el fondo del acento con texto en acento suave;
  - los demás botones van en superficie 2.
- **Tipografía:** título de página de 15 pt en semibold, títulos de sección de 11 pt, cuerpo de 10 pt.
- **Inicio:**
  - saludo "Hola" en grande;
  - tarjeta-botón grande "Nuevo trabajo" en acento, con icono;
  - favoritos como **chips** clicables (en lugar de la lista).
- **Configuración:** las secciones van en tarjetas con esquinas de 12 px (`QFrame#card`) en lugar de `QGroupBox`.

## 3. Fuera de alcance

Automatizar la app de Gemini, Gemini por API, tarjetas de resumen, historial y tema claro.

## 4. Pruebas clave

- `DownloadWatch`:
  - detecta un PNG nuevo solo cuando su tamaño se mantiene en dos sondeos;
  - ignora los `.crdownload` y los archivos anteriores a `since`;
  - entre dos archivos nuevos, elige el más reciente;
  - devuelve None en una carpeta inexistente.
- **Botón Gemini:**
  - el portapapeles contiene una imagen con las dimensiones del original (con el tope de 3072);
  - en modo `"desktop"` no se abre ninguna URL; en `"web"` se abre `gemini_url`;
  - no se llama a `reveal`;
  - la imagen queda en espera.
- **Vigilancia de punta a punta (UI):**
  - tras pulsar el botón, se escribe un PNG en `downloads_dir` y se avanza el reloj de sondeo → la imagen en espera queda mejorada con "Gemini" aunque la selección haya cambiado;
  - la espera termina tras recibir el archivo.
- **Ctrl+V:**
  - con una imagen de 2304×4096 en el portapapeles → se adjunta;
  - con la misma imagen original → aparece el aviso y no se adjunta nada;
  - con el portapapeles vacío → aparece el aviso correspondiente.
- **Estilo:**
  - los iconos SVG existen y `icon()` devuelve un `QIcon` no nulo;
  - la barra lateral tiene iconos y el encabezado de marca;
  - el QSS contiene el acento `#7c5cff`;
  - Inicio muestra los favoritos como botones;
  - `test_no_dead_buttons` sigue en verde;
  - el panel sigue cabiendo a 1366×697.
- **Capturas offscreen** para revisar el estilo antes de entregar.
