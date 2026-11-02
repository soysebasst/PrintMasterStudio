@echo off
REM Doble clic para crear el acceso directo de PrintMaster Studio en el Escritorio y en Inicio.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\crear_acceso_directo.ps1"
pause
