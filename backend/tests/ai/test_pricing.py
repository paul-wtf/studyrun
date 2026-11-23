from decimal import Decimal

import pytest

from studyrun.ai.pricing import UnknownModel, Usage, cost_usd

OPUS = "claude-opus-5-5"


def test_cost_opus():
    usage = Usage(1_000_000, 100_000, 0, 0)
    assert cost_usd(OPUS, usage) == Decimal("6.000000")


def test_cost_cache():
    usage = Usage(0, 0, 500_000, 100_000)
    assert cost_usd(OPUS, usage) == Decimal("0.600000")


def test_cost_batch_half():
    usage = Usage(1_000_000, 100_000, 0, 0)
    assert cost_usd(OPUS, usage, batch=True) == Decimal("3.000000")


def test_unknown_model_raises():
    with pytest.raises(UnknownModel):
        cost_usd("gpt-nope", Usage(1, 1, 0, 0))
