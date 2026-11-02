# PrintMaster Studio

Prepara imágenes y genera **un PDF por imagen** con dimensiones físicas exactas,
optimizado para el plotter Epson SureColor SC-T3170.

## Desarrollo

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m printmaster      # abrir la aplicación
pytest -q                  # ejecutar pruebas
ruff check .               # revisar estilo
```

Ver `PROGRESS.md` para el estado del desarrollo.
