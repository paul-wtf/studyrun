from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.pricing import Usage, cost_usd
from studyrun.models.db import ApiCall, Feature


async def record_call(
    session: AsyncSession,
    feature: Feature,
    model: str,
    usage: Usage,
    now: datetime,
    *,
    batch: bool = False,
) -> Decimal:
    cost = cost_usd(model, usage, batch=batch)
    session.add(
        ApiCall(
            at=now,
            feature=feature,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            batch=batch,
            cost_usd=cost,
        )
    )
    await session.flush()
    return cost


async def spent(
    session: AsyncSession, features: set[Feature], start: datetime, end: datetime
) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(ApiCall.cost_usd), 0)).where(
            ApiCall.feature.in_(features), ApiCall.at >= start, ApiCall.at < end
        )
    )
    return total if total is not None else Decimal(0)
