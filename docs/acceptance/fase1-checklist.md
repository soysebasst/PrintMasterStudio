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
