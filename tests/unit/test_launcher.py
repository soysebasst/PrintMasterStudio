import tomllib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def test_gui_script_declared():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["gui-scripts"]["printmaster-studio"] == "printmaster.app:main"


def test_icon_has_256():
    ico = ROOT / "src/printmaster/ui/assets/printmaster.ico"
    with Image.open(ico) as img:
        assert (256, 256) in img.info.get("sizes", {img.size})


def test_shortcut_script():
    text = (ROOT / "tools/crear_acceso_directo.ps1").read_text(encoding="utf-8")
    assert "printmaster-studio.exe" in text and "Desktop" in text and "Programs" in text
    assert (ROOT / "crear_acceso_directo.bat").exists()
