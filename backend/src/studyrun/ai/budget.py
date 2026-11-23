from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.clock import local_day_bounds
from studyrun.ai.ledger import spent
from studyrun.config import Settings
from studyrun.models.db import Feature

_GENERATION = {Feature.generate, Feature.verify}
_INTERACTIVE = {Feature.grade, Feature.tutor}


class BudgetExceeded(Exception):
    def __init__(self, feature: Feature, spent: Decimal, cap: Decimal):
        super().__init__(f"daily budget for {feature.value} reached: {spent} of {cap} USD")
        self.feature = feature
        self.spent = spent
        self.cap = cap


async def ensure_budget(
    session: AsyncSession, feature: Feature, settings: Settings, now: datetime
) -> None:
    if feature in _GENERATION:
        group, cap = _GENERATION, Decimal(str(settings.generation_daily_budget_usd))
    else:
        group, cap = _INTERACTIVE, Decimal(str(settings.daily_ai_cap_usd))
    start, end = local_day_bounds(now, settings.timezone)
    total = await spent(session, group, start, end)
    if total >= cap:
        raise BudgetExceeded(feature, total, cap)
