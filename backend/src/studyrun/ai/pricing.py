from dataclasses import dataclass
from decimal import Decimal

from studyrun.config import PRICES

_PER_MILLION = Decimal(1_000_000)
_QUANT = Decimal("0.000001")


class UnknownModel(Exception):
    pass


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


def cost_usd(model: str, usage: Usage, *, batch: bool = False) -> Decimal:
    price = PRICES.get(model)
    if price is None:
        raise UnknownModel(model)
    total = (
        usage.input_tokens * Decimal(str(price.input))
        + usage.output_tokens * Decimal(str(price.output))
        + usage.cache_read_tokens * Decimal(str(price.cache_read))
        + usage.cache_write_tokens * Decimal(str(price.cache_write))
    ) / _PER_MILLION
    if batch:
        total /= 2
    return total.quantize(_QUANT)
