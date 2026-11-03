import os
import time

from PIL import Image

from printmaster.core.enhance.download_watch import DownloadWatch
from printmaster.infra.settings import Settings


def png(path, size=(20, 10), mtime=None):
    Image.new("RGB", size, (1, 2, 3)).save(path)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_detects_only_when_stable(tmp_path):
    w = DownloadWatch(tmp_path, since=time.time() - 1)
    f = png(tmp_path / "Gemini_Generated_Image.png")
    assert w.poll() is None  # primer sondeo: se registra el tamaño
    assert w.poll() == f  # segundo sondeo con el mismo tamaño


def test_growing_file_waits(tmp_path):
    w = DownloadWatch(tmp_path, since=time.time() - 1)
    f = tmp_path / "g.png"
    f.write_bytes(b"\x89PNG" + b"0" * 10)
    assert w.poll() is None
    f.write_bytes(b"\x89PNG" + b"0" * 50)
    assert w.poll() is None
    assert w.poll() == f


def test_ignores_partial_and_old(tmp_path):
    since = time.time()
    png(tmp_path / "vieja.png", mtime=since - 100)
    (tmp_path / "x.png.crdownload").write_bytes(b"abc")
    (tmp_path / "vacia.png").write_bytes(b"")
    w = DownloadWatch(tmp_path, since=since)
    assert w.poll() is None and w.poll() is None


def test_picks_newest(tmp_path):
    since = time.time() - 10
    png(tmp_path / "a.png", mtime=since + 1)
    b = png(tmp_path / "b.png", mtime=since + 5)
    w = DownloadWatch(tmp_path, since=since)
    w.poll()
    assert w.poll() == b


def test_missing_folder(tmp_path):
    w = DownloadWatch(tmp_path / "no_existe", since=0)
    assert w.folder_ok is False and w.poll() is None


def test_settings_defaults():
    s = Settings()
    assert s.gemini_open_mode == "desktop"
    assert s.downloads_dir.name == "Downloads"
    assert s.gemini_url.startswith("https://gemini.google.com")
