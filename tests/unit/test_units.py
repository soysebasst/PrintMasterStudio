from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from printmaster.domain.units import Unit, effective_ppi, from_mm, mm_to_pt, mm_to_px, to_mm


def test_to_mm_cm():
    assert to_mm(60, Unit.CM) == Decimal("600")


def test_to_mm_inches():
    assert to_mm(24, Unit.IN) == Decimal("609.6")


@given(
    st.decimals(min_value=Decimal("0.1"), max_value=Decimal("10000"), places=2),
    st.sampled_from(list(Unit)),
)
def test_roundtrip(value, unit):
    assert from_mm(to_mm(value, unit), unit) == Decimal(str(value))


def test_mm_to_pt():
    assert abs(mm_to_pt(Decimal(600)) - 1700.7874) < 0.001


def test_mm_to_px():
    assert mm_to_px(Decimal(600), 200) == 4724
    assert mm_to_px(Decimal(900), 200) == 7087


def test_effective_ppi():
    assert abs(effective_ppi(4724, Decimal(600)) - 199.99) < 0.05
