import pytest

from printmaster.domain.quality import QualityLevel, classify, downgrade


@pytest.mark.parametrize(
    "ppi,level",
    [
        (250, QualityLevel.EXCELENTE),
        (249.9, QualityLevel.BUENA),
        (180, QualityLevel.BUENA),
        (179.9, QualityLevel.ACEPTABLE),
        (120, QualityLevel.ACEPTABLE),
        (72, QualityLevel.BAJA),
        (71.9, QualityLevel.MUY_BAJA),
    ],
)
def test_classify_limits(ppi, level):
    assert classify(ppi) == level


def test_downgrade():
    assert downgrade(QualityLevel.BUENA) == QualityLevel.ACEPTABLE
    assert downgrade(QualityLevel.MUY_BAJA) == QualityLevel.MUY_BAJA
