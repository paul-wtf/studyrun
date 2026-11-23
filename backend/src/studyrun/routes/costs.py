from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from studyrun.ai.clock import local_day_bounds, local_month_bounds
from studyrun.config import Settings
from studyrun.deps import get_now, get_settings
from studyrun.models.db import ApiCall, Feature
from studyrun.routes.modules import Session

router = APIRouter()

_GENERATION = (Feature.generate, Feature.verify)
_INTERACTIVE = (Feature.grade, Feature.tutor)


class Period(BaseModel):
    total: float
    by_feature: dict[str, float]


class CostsOut(BaseModel):
    today: Period
    month: Period
    cap_today: float
    remaining_today: float
    generation_budget_today: float
    generation_remaining_today: float


async def _period(session: Session, start: datetime, end: datetime) -> dict[Feature, Decimal]:
    rows = await session.execute(
        select(ApiCall.feature, func.sum(ApiCall.cost_usd))
        .where(ApiCall.at >= start, ApiCall.at < end)
        .group_by(ApiCall.feature)
    )
    totals = {feature: Decimal(0) for feature in Feature}
    totals.update({feature: total for feature, total in rows.all()})
    return totals


def _out(totals: dict[Feature, Decimal]) -> Period:
    return Period(
        total=float(sum(totals.values())),
        by_feature={feature.value: float(totals[feature]) for feature in Feature},
    )


def _remaining(cap: float, totals: dict[Feature, Decimal], features: tuple[Feature, ...]) -> float:
    return max(0.0, float(Decimal(str(cap)) - sum(totals[f] for f in features)))


@router.get("/costs")
async def costs(
    session: Session,
    now: Annotated[datetime, Depends(get_now)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CostsOut:
    today = await _period(session, *local_day_bounds(now, settings.timezone))
    month = await _period(session, *local_month_bounds(now, settings.timezone))
    return CostsOut(
        today=_out(today),
        month=_out(month),
        cap_today=settings.daily_ai_cap_usd,
        remaining_today=_remaining(settings.daily_ai_cap_usd, today, _INTERACTIVE),
        generation_budget_today=settings.generation_daily_budget_usd,
        generation_remaining_today=_remaining(
            settings.generation_daily_budget_usd, today, _GENERATION
        ),
    )
