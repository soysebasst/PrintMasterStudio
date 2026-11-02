from decimal import Decimal

from printmaster.domain.models import CropOffset, Orientation, PrintSpec


def test_auto_orientation_follows_landscape_image():
    s = PrintSpec(Decimal(600), Decimal(900)).resolved_for(4000, 3000)
    assert (s.width_mm, s.height_mm) == (Decimal(900), Decimal(600))
    assert s.orientation == Orientation.LANDSCAPE


def test_auto_orientation_follows_portrait_image():
    s = PrintSpec(Decimal(900), Decimal(600)).resolved_for(3000, 4000)
    assert (s.width_mm, s.height_mm) == (Decimal(600), Decimal(900))


def test_forced_portrait():
    s = PrintSpec(Decimal(600), Decimal(900), orientation=Orientation.PORTRAIT).resolved_for(
        4000, 3000
    )
    assert (s.width_mm, s.height_mm) == (Decimal(600), Decimal(900))


def test_square_image_keeps_spec():
    s = PrintSpec(Decimal(600), Decimal(900)).resolved_for(1000, 1000)
    assert (s.width_mm, s.height_mm) == (Decimal(600), Decimal(900))
    assert s.orientation != Orientation.AUTO


def test_crop_offset_clamped():
    assert CropOffset(1.5, -2) == CropOffset(1.0, 0.0)
