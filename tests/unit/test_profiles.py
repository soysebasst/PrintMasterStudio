from decimal import Decimal as D

import pytest

from printmaster.domain.models import Orientation, PrintSpec
from printmaster.printers.profiles import list_profiles, load_profile, validate


def spec(w, h):
    # Orientación forzada para que el "ancho" sea exactamente el dado.
    o = Orientation.LANDSCAPE if w > h else Orientation.PORTRAIT
    return PrintSpec(D(w), D(h), orientation=o)


def test_load_profile():
    assert load_profile().roll_max_mm == 610


def test_list_profiles():
    assert "epson_sc_t3170" in {p.id for p in list_profiles()}


@pytest.mark.parametrize(
    "w,h,codes",
    [
        (600, 900, []),
        (606, 900, ["margin"]),
        (900, 600, ["rotate"]),
        (700, 700, ["too_wide"]),
        (600, 6000, ["too_long"]),
        (0, 900, ["invalid"]),
    ],
)
def test_validate(w, h, codes):
    issues = validate(spec(w, h), load_profile())
    assert [i.code for i in issues] == codes


def test_messages_in_spanish():
    (issue,) = validate(spec(700, 700), load_profile())
    assert issue.level == "error"
    assert issue.message == "Ningún lado cabe en la impresora (máx. 610 mm de ancho)."
