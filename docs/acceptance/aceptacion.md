# Fase 1 — Checklist de aceptación en Windows

Hazlo en el PC donde vas a usar la app. Marca cada punto y anota tiempos y fallos al final.

## 1. Instalación (solo la primera vez)

1. Instala **Python 3.12 (64 bits)** desde python.org. En el instalador marca *"Add python.exe to PATH"*.
2. Instala **Git for Windows** (git-scm.com) si no lo tienes.
3. Abre **PowerShell** en la carpeta donde quieras el proyecto y ejecuta:

```powershell
git clone https://github.com/soysebasst/PrintMasterStudio.git
cd PrintMasterStudio
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
```

## 2. Abrir la aplicación

```powershell
.venv\Scripts\python -m printmaster
```

- [ ] La ventana abre en tema oscuro con **Inicio / Nuevo trabajo / Configuración**.

## 3. Flujo real

- [ ] En *Nuevo trabajo*, arrastra **20 imágenes reales** de clientes (incluye fotos de celular, un PNG con fondo transparente y un archivo con tildes o ñ en el nombre).
- [ ] Aparecen las miniaturas y cada imagen recibe su insignia de calidad (Exc/Bue/Ace/Baj/MBaj).
- [ ] Elige **60 × 90 cm**. El lienzo muestra la página a escala y el PPI efectivo.
- [ ] Prueba los tres modos: **Ajustar sin recortar**, **Rellenar** (blanco, color, color del borde y difuminado) y **Recortar** (arrastra la imagen para mover el recorte).
- [ ] Las fotos de celular se ven derechas, no giradas.
- [ ] **Aprobar todo** y luego **Exportar PDF**. Al terminar aparece "N PDF generados" y **Abrir carpeta** abre la carpeta del día.

## 4. Verificar medidas

- [ ] Abre 3 PDF en **Adobe Acrobat Reader** → *Archivo › Propiedades*: el tamaño de página es **60 × 90 cm** (o 90 × 60 si la imagen es horizontal).
- [ ] Imprime **1 pieza** en la SC-T3170. En el diálogo de impresión de Acrobat elige **"Tamaño real"**; nunca "Ajustar".
- [ ] Mide la impresión con regla o flexómetro. Tolerancia: **±1 mm**.

## 5. Dónde quedan las cosas

| Qué | Ubicación |
|---|---|
| PDF | `Documentos\PrintMaster\AAAA-MM-DD\` (cambiable en Configuración) |
| Configuración | `%APPDATA%\PrintMasterStudio\settings.json` |
| Registro de errores | `%LOCALAPPDATA%\PrintMasterStudio\logs\printmaster.log` |

## 6. Notas de la prueba

| Dato | Valor |
|---|---|
| PC / procesador / RAM | |
| Tiempo para cargar 20 imágenes | |
| Tiempo para exportar 20 PDF | |
| Medida real de la pieza impresa | |
| Fallos o cosas incómodas | |

Cuando termines, envíame esta tabla. La Fase 1 se da por cerrada solo con tu confirmación.

---

# Fase 2A — Lámina de 60 cm, precio sugerido y mejora con IA

## 1. Actualizar

```powershell
cd C:\PrintMaster
git pull
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m printmaster
```

## 2. Instalar el motor de mejora (una sola vez)

- [ ] *Configuración › Mejora con IA › **Instalar motor de mejora*** (descarga ≈45 MB del sitio oficial de Real-ESRGAN).
- [ ] Anota el mensaje que aparece: **"✓ Motor listo"** o el aviso de que el equipo no tiene aceleración compatible (en ese caso se usa la mejora básica).
- [ ] Opcional, para verificar el motor real: `.venv\Scripts\pytest -m gpu -q`. Debe decir `1 passed`.

## 3. Probar con tus dos imágenes

- [ ] Carga la del planeta (554×554) y la de "Respeto" (236×420).
- [ ] El modo es **"Ajustar largo a la imagen"**. El planeta queda en **60 × 60 cm · $12.000** y Respeto en **60 × 110 cm · $17.000**. Abajo dice **"2 láminas · $29.000"**.
- [ ] Cada imagen muestra la insignia **IA** al terminar de mejorarse. Usa **Ver original / Ver mejorada** para comparar.
- [ ] Anota cuánto tarda la mejora de cada una.
- [ ] Exporta, abre el PDF en Acrobat (60 × 110 cm) e imprime "Respeto" a **"Tamaño real"**. Compara la calidad con la impresión de la Fase 1.

| Dato | Valor |
|---|---|
| Mensaje del motor | |
| Tiempo de mejora (planeta / respeto) | |
| ¿Se ve mejor impresa? | |
| Medida real de la pieza | |
| Comentarios | |

---

# Fase 2B — Gemini web, interfaz nueva y acceso directo

## 1. Actualizar y crear el acceso directo

```powershell
cd C:\PrintMaster
git pull
.venv\Scripts\pip install -e ".[dev]"
```

- [ ] Doble clic en **`crear_acceso_directo.bat`**. Debe decir "Acceso directo creado en: …Desktop" y "…Programs".
- [ ] Abre la app desde el icono **PrintMaster Studio** del Escritorio, sin que aparezca una consola.

## 2. Interfaz

- [ ] Los pasos de arriba (Cargar → Revisar → Exportar) cambian solos.
- [ ] Abajo, "Siguiente:" te indica qué hacer.
- [ ] Las tarjetas muestran nombre, tamaño, precio y estado. El clic derecho tiene Quitar, Subir, Bajar y Abrir carpeta.
- [ ] El panel derecho cabe sin barra de desplazamiento. "Opciones avanzadas" está plegado y recuerda si lo abriste.

## 3. Gemini

- [ ] Selecciona "Respeto" y pulsa **Mejorar en Gemini**. Se abren Gemini y la carpeta, y el prompt queda copiado.
- [ ] Sube la imagen a Gemini, pega con Ctrl+V y descarga el resultado.
- [ ] Suelta el archivo en **«Suelta aquí la mejorada»**. Debe quedar en 60 × 110 cm a $17.000, con la insignia **Gemini** y "Mejorada con Gemini (web)…".
- [ ] Compara con los botones **Original / Mejorada**.
- [ ] Exporta, imprime a "Tamaño real" y compara con las impresiones anteriores.

| Dato | Valor |
|---|---|
| ¿El acceso directo abre sin consola? | |
| ¿La interfaz es más clara? ¿Qué falta? | |
| Resultado impreso con Gemini | |
| Comentarios | |


---

# Fase 2C — Gemini en menos pasos y estilo morado

## 1. Actualizar

```powershell
cd C:\PrintMaster
git pull
.venv\Scripts\pip install -e ".[dev]"
```

## 2. Configurar Gemini (una vez)

- [ ] Configuración › Gemini: elige «Solo copiar (uso la app de escritorio, Alt+Espacio)» o «Abrir Gemini en el navegador».
- [ ] Opcional: en Gemini crea un Gem (Gems › Nuevo Gem), pega lo que copia «Copiar instrucciones» y guarda. Pega la dirección del Gem en «Dirección de Gemini o de su Gem».
- [ ] Revisa que «Carpeta de descargas» sea la carpeta donde guarda el navegador/la app.

## 3. Flujo

- [ ] Selecciona una imagen y pulsa **Mejorar en Gemini**. Aparece «Esperando descarga de Gemini…».
- [ ] En Gemini: Ctrl+V, enviar.
- [ ] Prueba A: descarga el resultado. Debe adjuntarse solo en unos segundos («Mejora recibida de Gemini…»).
- [ ] Prueba B: en otra imagen, copia el resultado (clic derecho › Copiar imagen) y pulsa Ctrl+V en la app.
- [ ] Prueba C: pulsa Ctrl+V sin copiar el resultado → aviso de que el portapapeles tiene la original.
- [ ] Revisa largo, precio, insignia **Gemini**, exporta e imprime a «Tamaño real».

| Dato | Valor |
|---|---|
| ¿La descarga se detectó sola? | |
| ¿Ctrl+V funcionó desde la app de escritorio de Gemini? | |
| ¿El nuevo estilo se ve bien? | |
| Comentarios | |


---

# Fase 2D — recorte manual, solo Gemini y precio a la vista

## 1. Actualizar

```powershell
cd C:\PrintMaster
git pull
.venv\Scripts\pip install -e ".[dev]"
```

## 2. Probar

- [ ] Carga una imagen: ya no se mejora sola y no aparece «Mejora: Automática».
- [ ] Debajo de la zona de Gemini se ve el cuadro **Precio sugerido** con el tamaño de la lámina.
- [ ] Pulsa **Recortar**, deja «Libre», sube el borde de abajo y mira cómo cambian el largo y el precio. **Aplicar recorte**: la vista previa, la tarjeta y el total cambian.
- [ ] Recorta con la proporción «60 × 90 cm»: la lámina debe quedar exactamente en 60 × 90.
- [ ] **Restablecer** vuelve a la imagen completa.
- [ ] Copia para Gemini una imagen PNG grande: la app no se congela («Copiando imagen…»).
- [ ] Pega con Ctrl+V una imagen copiada de Gemini: debe avisar que es una copia reducida. Descárgala y compara.
- [ ] Exporta una recortada e imprímela a «Tamaño real».

| Dato | Valor |
|---|---|
| ¿El recorte es cómodo? | |
| ¿El precio se entiende a simple vista? | |
| Comentarios | |


---

# Fase 2E — largo justo, girar dentro de la lámina, ventana más limpia

## 1. Actualizar

```powershell
cd C:\PrintMaster
git pull
.venv\Scripts\pip install -e ".[dev]"
```

## 2. Probar

- [ ] Inicio muestra solo el botón «Nuevo trabajo».
- [ ] Una imagen casi cuadrada en «Largo auto»: la lámina sale al milímetro (ej. 60 × 61,3) y sin franjas blancas; el precio es el del tramo de 5 cm.
- [ ] Escribe otro largo (ej. 55): pasa a «Recortar» y puedes arrastrar la imagen para elegir qué se corta.
- [ ] Una imagen horizontal con tamaño 60 × 90 y «Ajustar»: sale girada llenando la lámina, con «Girar 90°» marcado y «· Girada» abajo.
- [ ] El botón «Girar 90°» la gira o la deja derecha a mano.
- [ ] En «Opciones avanzadas» ya no aparecen Orientación ni Resolución; la resolución se cambia en Configuración.
- [ ] Exporta una girada y una de largo justo e imprímelas a «Tamaño real».
