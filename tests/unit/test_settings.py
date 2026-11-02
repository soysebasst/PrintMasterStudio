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
    assert s.favorites[0].name == "60 × 45 cm"
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
