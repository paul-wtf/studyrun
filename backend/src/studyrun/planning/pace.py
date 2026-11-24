from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.clock import local_day_bounds
from studyrun.config import Settings
from studyrun.models.db import ReviewLog

WINDOW_DAYS = 28
MIN_STUDY_DAYS = 7


async def measured_pace(session: AsyncSession, settings: Settings, now: datetime) -> float:
    _, end = local_day_bounds(now, settings.timezone)
    first_day = now.astimezone(ZoneInfo(settings.timezone)) - timedelta(days=WINDOW_DAYS - 1)
    start, _ = local_day_bounds(first_day, settings.timezone)
    local_day = cast(func.timezone(settings.timezone, ReviewLog.answered_at), Date)
    study_days = await session.scalar(
        select(func.count(func.distinct(local_day))).where(
            ReviewLog.answered_at >= start, ReviewLog.answered_at < end
        )
    )
    first_seen = (
        select(func.min(ReviewLog.answered_at).label("at")).group_by(ReviewLog.item_id).subquery()
    )
    learned = await session.scalar(
        select(func.count())
        .select_from(first_seen)
        .where(first_seen.c.at >= start, first_seen.c.at < end)
    )
    if (study_days or 0) >= MIN_STUDY_DAYS and learned:
        return learned / WINDOW_DAYS
    return float(max(settings.run_new_items, 1))
