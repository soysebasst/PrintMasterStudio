import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def settings(tmp_path):
    from printmaster.infra.settings import load_settings
    s = load_settings()
    s.output_dir = tmp_path / "salida"
    return s


@pytest.fixture(autouse=True)
def drain_thread_pool():
    """Que ninguna tarea de fondo de una prueba se filtre a la siguiente."""
    yield
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(15000)
