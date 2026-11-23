from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from studyrun.ai.ledger import record_call, spent
from studyrun.ai.pricing import Usage
from studyrun.models.db import ApiCall, Feature

NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)
START = datetime(2026, 11, 23, tzinfo=UTC)
END = datetime(2026, 11, 24, tzinfo=UTC)


async def test_record_call_stores_row_and_returns_cost(db_session):
    cost = await record_call(
        db_session, Feature.grade, "claude-opus-5-5", Usage(1_000_000, 0, 0, 0), NOW
    )
    assert cost == Decimal("4.000000")
    row = (await db_session.execute(select(ApiCall))).scalar_one()
    assert row.cost_usd == Decimal("4.000000")
    assert row.feature == Feature.grade
    assert row.batch is False
    assert row.at == NOW


async def test_record_call_batch_flag(db_session):
    cost = await record_call(
        db_session, Feature.generate, "claude-opus-5-5", Usage(1_000_000, 0, 0, 0), NOW, batch=True
    )
    assert cost == Decimal("2.000000")
    row = (await db_session.execute(select(ApiCall))).scalar_one()
    assert row.batch is True


async def test_spent_filters_feature_and_window(db_session):
    usage = Usage(250_000, 0, 0, 0)
    await record_call(db_session, Feature.grade, "claude-opus-5-5", usage, NOW)
    await record_call(db_session, Feature.tutor, "claude-opus-5-5", usage, NOW)
    await record_call(db_session, Feature.generate, "claude-opus-5-5", usage, NOW)
    await record_call(db_session, Feature.grade, "claude-opus-5-5", usage, END)
    total = await spent(db_session, {Feature.grade, Feature.tutor}, START, END)
    assert total == Decimal("2.000000")


async def test_spent_empty_is_zero(db_session):
    assert await spent(db_session, {Feature.grade}, START, END) == Decimal(0)
