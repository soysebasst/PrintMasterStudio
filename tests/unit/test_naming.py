from datetime import date
from pathlib import Path

from printmaster.core.naming import NamingOptions, output_path, sanitize, unique_path

TODAY = date(2026, 11, 2)


def test_default_layout(tmp_path):
    p = output_path(tmp_path, 0, Path("a.jpg"), NamingOptions(client="Peña"), TODAY)
    assert p == tmp_path / "2026-11-02" / "Peña" / "Cliente_001.pdf"


def test_numbering_and_digits(tmp_path):
    p = output_path(tmp_path, 41, Path("a.jpg"), NamingOptions(), TODAY)
    assert p.name == "Cliente_042.pdf"
    assert output_path(tmp_path, 0, Path("a.jpg"), NamingOptions(digits=4), TODAY).name == (
        "Cliente_0001.pdf"
    )


def test_no_date_no_client(tmp_path):
    p = output_path(tmp_path, 0, Path("a.jpg"), NamingOptions(by_date=False), TODAY)
    assert p == tmp_path / "Cliente_001.pdf"


def test_original_name(tmp_path):
    p = output_path(tmp_path, 3, Path("foto final.png"),
                    NamingOptions(use_original_name=True, by_date=False), TODAY)
    assert p.name == "foto final.pdf"


def test_sanitize():
    assert sanitize('a:b*?.') == "ab"
    assert sanitize("CON") == "CON_"
    assert sanitize("  ") == "sin_nombre"
    assert sanitize("ok\x01name") == "okname"


def test_sanitized_client_and_prefix(tmp_path):
    p = output_path(tmp_path, 0, Path("a.jpg"),
                    NamingOptions(prefix="Ped/ido", client="A:B", by_date=False), TODAY)
    assert p == tmp_path / "AB" / "Pedido_001.pdf"


def test_unique_path(tmp_path):
    (tmp_path / "x.pdf").write_text("")
    (tmp_path / "x_2.pdf").write_text("")
    assert unique_path(tmp_path / "x.pdf") == tmp_path / "x_3.pdf"
    assert unique_path(tmp_path / "nuevo.pdf") == tmp_path / "nuevo.pdf"
