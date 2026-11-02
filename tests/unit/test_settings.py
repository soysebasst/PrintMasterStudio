from decimal import Decimal

import pytest
from pydantic import ValidationError

from printmaster.infra import paths
from printmaster.infra.settings import Settings, load_settings, save_settings


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path))
    return tmp_path


def test_paths_under_home(home):
    assert paths.config_dir() == home / "config" and paths.config_dir().is_dir()
    assert paths.data_dir() == home / "data"
    assert paths.default_output_dir() == home / "output"


def test_defaults():
    s = load_settings()
    assert len(s.favorites) == 6
    assert s.favorites[0].name == "60 × 30 cm"
    assert s.favorites[0].width == Decimal(60)
    assert s.default_ppi == 200


def test_roundtrip():
    s = load_settings()
    s.naming_prefix = "Pedido"
    save_settings(s)
    assert load_settings() == s


def test_corrupt_file_backed_up(home):
    f = paths.config_dir() / "settings.json"
    f.write_text("{ esto no es json")
    s = load_settings()
    assert s.default_ppi == 200
    assert (paths.config_dir() / "settings.json.bak").exists()


def test_invalid_ppi():
    with pytest.raises(ValidationError):
        Settings(output_dir=".", default_ppi=1000)


def test_v1_settings_migrated(home):
    import json

    from printmaster.domain.models import FitMode, Orientation
    f = paths.config_dir() / "settings.json"
    f.write_text(json.dumps({
        "output_dir": str(home / "salida"), "default_ppi": 200, "default_unit": "cm",
        "default_mode": "ajustar", "naming_prefix": "Pedido",
        "favorites": [{"name": "Mío", "width": 50, "height": 70, "unit": "cm"}],
    }))
    s = load_settings()
    assert s.default_mode == FitMode.FIT_LENGTH
    assert s.default_orientation == Orientation.AS_ENTERED
    assert s.roll_width_mm == 600
    assert s.naming_prefix == "Pedido"
    assert [x.name for x in s.favorites] == ["Mío"]
    assert s.settings_version == 2


def test_v2_settings_not_remigrated():
    from printmaster.domain.models import FitMode
    s = load_settings()
    s.default_mode = FitMode.CONTAIN
    save_settings(s)
    assert load_settings().default_mode == FitMode.CONTAIN


def test_new_default_favorites():
    assert [f.name for f in load_settings().favorites] == [
        "60 × 30 cm", "60 × 45 cm", "60 × 60 cm", "60 × 90 cm", "60 × 120 cm", "60 × 150 cm"]


def test_pricing_config():
    assert Settings(price_long=20000).pricing().price_long == 20000
    assert Settings().pricing().price_short == 10000


def test_roll_width_range():
    with pytest.raises(ValidationError):
        Settings(roll_width_mm=700)
