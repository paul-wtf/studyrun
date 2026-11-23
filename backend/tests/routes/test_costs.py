from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from studyrun.deps import get_now
from studyrun.models.db import ApiCall, Feature

BERLIN = ZoneInfo("Europe/Berlin")


def berlin(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=BERLIN).astimezone(UTC)


async def add(db_session, feature, cost, at):
    db_session.add(
        ApiCall(
            at=at,
            feature=feature,
            model="claude-opus-5-5",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            batch=False,
            cost_usd=Decimal(cost),
        )
    )
    await db_session.flush()


async def test_costs_today_and_month_berlin(api, db_session):
    client, app = api
    app.dependency_overrides[get_now] = lambda: berlin(11, 23, 10)
    await add(db_session, Feature.grade, "0.10", berlin(11, 23, 0, 30))
    await add(db_session, Feature.grade, "0.05", berlin(11, 23, 9))
    await add(db_session, Feature.generate, "3.00", berlin(11, 23, 8))
    await add(db_session, Feature.verify, "1.00", berlin(11, 23, 9))
    await add(db_session, Feature.grade, "0.20", berlin(11, 22, 23, 30))
    await add(db_session, Feature.generate, "2.00", berlin(11, 1, 0, 10))
    await add(db_session, Feature.generate, "9.00", berlin(10, 31, 23, 30))
    resp = await client.get("/api/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today"]["total"] == 4.15
    assert data["today"]["by_feature"] == {
        "generate": 3.0,
        "verify": 1.0,
        "grade": 0.15,
        "tutor": 0.0,
    }
    assert data["month"]["total"] == 6.35
    assert data["month"]["by_feature"]["generate"] == 5.0
    assert data["cap_today"] == 0.5
    assert data["remaining_today"] == 0.35
    assert data["generation_budget_today"] == 10.0
    assert data["generation_remaining_today"] == 6.0


async def test_costs_remaining_never_negative(api, db_session):
    client, app = api
    app.dependency_overrides[get_now] = lambda: berlin(11, 23, 10)
    await add(db_session, Feature.grade, "0.70", berlin(11, 23, 9))
    await add(db_session, Feature.generate, "12.00", berlin(11, 23, 9))
    data = (await client.get("/api/costs")).json()
    assert data["remaining_today"] == 0.0
    assert data["generation_remaining_today"] == 0.0
