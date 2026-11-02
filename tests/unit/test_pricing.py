from decimal import Decimal as D

import pytest

from printmaster.core.pricing import PricingConfig, format_cop, suggest_price


@pytest.mark.parametrize("length,price", [
    (450, 10000), (900, 15000), (600, 12000), (1100, 17000), (1800, 25000), (200, 10000),
])
def test_examples(length, price):
    assert suggest_price(D(600), D(length)) == price


def test_narrower_width_scales_by_area():
    assert suggest_price(D(300), D(900)) == 10000


def test_half_rounds_up():
    assert suggest_price(D(600), D(450), PricingConfig(price_short=10500)) == 11000


def test_configurable():
    assert suggest_price(D(600), D(900), PricingConfig(price_long=20000)) == 20000


def test_format_cop():
    assert format_cop(17000) == "$17.000"
    assert format_cop(1250000) == "$1.250.000"
