# Crea accesos directos de PrintMaster Studio en el Escritorio y en el menú Inicio.
# Uso: doble clic en crear_acceso_directo.bat (en la carpeta del proyecto).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root ".venv\Scripts\printmaster-studio.exe"
$icon = Join-Path $root "src\printmaster\ui\assets\printmaster.ico"
if (-not (Test-Path $exe)) {
    Write-Host "No se encontró $exe" -ForegroundColor Red
    Write-Host "Ejecute primero:  .venv\Scripts\pip install -e ." -ForegroundColor Yellow
    exit 1
}
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("ApplicationData")) "Microsoft\Windows\Start Menu\Programs")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "PrintMaster Studio.lnk"))
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = "PrintMaster Studio"
    $lnk.Save()
    Write-Host "Acceso directo creado en: $dir" -ForegroundColor Green
}
