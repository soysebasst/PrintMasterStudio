import threading
import time

import pytest
from PIL import Image

from printmaster.app_services.job_controller import JobController
from printmaster.core.enhance import gemini_web
from printmaster.core.enhance.enhancer import Enhancer
from printmaster.core.enhance.gemini_web import ENGINE_GEMINI
from printmaster.core.enhance.realesrgan import RealEsrgan
from printmaster.domain.models import EnhanceChoice
from printmaster.infra.settings import Settings
from printmaster.printers.profiles import load_profile


@pytest.fixture
def ctrl(tmp_path, monkeypatch, make_image):
    monkeypatch.setenv("PRINTMASTER_HOME", str(tmp_path / "home"))
    c = JobController(Settings(output_dir=tmp_path / "out"), load_profile())
    c.add_paths([make_image("respeto.jpg", size=(236, 420))])
    c.analyze(0)
    return c


def test_auto_enhance_does_not_overwrite_gemini(ctrl, tmp_path, fake_engine_cmd, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "1.5")
    enh = Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "cache")
    t = threading.Thread(target=lambda: ctrl.enhance(0, enh))
    t.start()
    time.sleep(0.3)
    g = tmp_path / "g.png"
    Image.new("RGB", (2304, 4096), (200, 100, 50)).save(g)
    ctrl.attach_external(0, g)  # sin pase local
    t.join(30)
    assert ctrl.items[0].enhanced.engine == ENGINE_GEMINI
    assert ctrl.source_info(0).width_px == 2304


def test_attach_local_pass_cancellable(ctrl, tmp_path, fake_engine_cmd, monkeypatch):
    monkeypatch.setenv("FAKE_ESRGAN_SLEEP", "5")
    g = tmp_path / "g.png"
    Image.new("RGB", (236, 420), (200, 100, 50)).save(g)
    ev = threading.Event()
    threading.Timer(0.3, ev.set).start()
    t0 = time.monotonic()
    res = ctrl.attach_external(0, g, Enhancer(RealEsrgan(fake_engine_cmd), tmp_path / "c"),
                               cancel=ev)
    assert time.monotonic() - t0 < 3
    assert res.result.engine == ENGINE_GEMINI  # se queda con la de Gemini sin pase local
    assert ctrl.items[0].enhance_choice != EnhanceChoice.OFF


def test_reveal_command_windows_quotes(monkeypatch):
    from pathlib import PureWindowsPath
    monkeypatch.setattr(gemini_web.sys, "platform", "win32")
    cmd = gemini_web.reveal_command(PureWindowsPath(r"C:\Fotos\WhatsApp Image 1.jpeg"))
    assert cmd == r'explorer /select,"C:\Fotos\WhatsApp Image 1.jpeg"'
