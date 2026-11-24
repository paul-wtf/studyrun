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


def test_cost_sonnet_cache_read():
    usage = Usage(0, 0, 1_000_000, 1_000_000)
    assert cost_usd("claude-sonnet-5-5", usage) == Decimal("2.600000")


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-opus-5", "30.000000"),
        ("claude-opus-4-8", "30.000000"),
        ("claude-sonnet-5", "12.000000"),
    ],
)
def test_fallback_models_are_priced(model, expected):
    assert cost_usd(model, Usage(1_000_000, 1_000_000, 0, 0)) == Decimal(expected)
