import hashlib
import io
import zipfile

import pytest

from printmaster.core.enhance.installer import find_engine, install_engine
from printmaster.core.enhance.realesrgan import EnhanceError, exe_name


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"realesrgan-ncnn-vulkan-20220424-windows/{exe_name()}", b"binario")
        z.writestr("realesrgan-ncnn-vulkan-20220424-windows/models/x.param", b"m")
    return buf.getvalue()


def opener_for(data):
    return lambda url: io.BytesIO(data)


def test_install_ok(tmp_path):
    data = make_zip()
    progress = []
    exe = install_engine(tmp_path, "https://x/y.zip", hashlib.sha256(data).hexdigest(),
                         opener=opener_for(data), progress=lambda a, b: progress.append(a))
    assert exe.exists() and exe.name == exe_name()
    assert find_engine(tmp_path) is not None
    assert progress


def test_bad_hash_installs_nothing(tmp_path):
    with pytest.raises(EnhanceError, match="hash distinto"):
        install_engine(tmp_path, "https://x/y.zip", "0" * 64, opener=opener_for(make_zip()))
    assert not (tmp_path / ".download.zip.tmp").exists()
    assert not (tmp_path / "current").exists()
    assert find_engine(tmp_path) is None


def test_reinstall_replaces(tmp_path):
    data = make_zip()
    sha = hashlib.sha256(data).hexdigest()
    install_engine(tmp_path, "u", sha, opener=opener_for(data))
    install_engine(tmp_path, "u", sha, opener=opener_for(data))
    assert find_engine(tmp_path) is not None


def test_find_engine_missing(tmp_path):
    assert find_engine(tmp_path / "nada") is None
