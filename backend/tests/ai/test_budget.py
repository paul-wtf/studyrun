from datetime import datetime

import pytest

from studyrun.ai.budget import BudgetExceeded, ensure_budget
from studyrun.ai.ledger import record_call
from studyrun.ai.pricing import Usage
from studyrun.config import Settings
from studyrun.models.db import Feature

NOW = datetime.fromisoformat("2026-11-23T12:00:00+01:00")
HALF_DOLLAR = Usage(125_000, 0, 0, 0)


async def test_budget_blocks_at_cap(db_session):
    await record_call(db_session, Feature.grade, "claude-opus-5-5", HALF_DOLLAR, NOW)
    with pytest.raises(BudgetExceeded) as exc:
        await ensure_budget(db_session, Feature.grade, Settings(), NOW)
    assert exc.value.feature == Feature.grade


async def test_budget_allows_below_cap(db_session):
    await ensure_budget(db_session, Feature.grade, Settings(), NOW)


async def test_budget_tutor_shares_cap_with_grade(db_session):
    await record_call(db_session, Feature.grade, "claude-opus-5-5", HALF_DOLLAR, NOW)
    with pytest.raises(BudgetExceeded):
        await ensure_budget(db_session, Feature.tutor, Settings(), NOW)


async def test_budget_ignores_yesterday(db_session):
    yesterday = datetime.fromisoformat("2026-11-22T23:59:00+01:00")
    await record_call(db_session, Feature.grade, "claude-opus-5-5", HALF_DOLLAR, yesterday)
    await ensure_budget(db_session, Feature.grade, Settings(), NOW)


async def test_generation_budget_separate(db_session):
    await record_call(db_session, Feature.grade, "claude-opus-5-5", HALF_DOLLAR, NOW)
    await ensure_budget(db_session, Feature.generate, Settings(), NOW)


async def test_generation_budget_shared_with_verify(db_session):
    big = Usage(2_500_000, 0, 0, 0)
    await record_call(db_session, Feature.verify, "claude-opus-5-5", big, NOW)
    with pytest.raises(BudgetExceeded) as exc:
        await ensure_budget(db_session, Feature.generate, Settings(), NOW)
    assert exc.value.cap == 10
