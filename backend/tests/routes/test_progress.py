from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from study.helpers import make_chapter, make_item, make_module, make_subject

from studyrun.deps import get_now
from studyrun.models.db import ChapterStatus, ReviewLog

BERLIN = ZoneInfo("Europe/Berlin")


def berlin(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=BERLIN).astimezone(UTC)


async def log_review(db_session, item, at: datetime) -> None:
    db_session.add(ReviewLog(item_id=item.id, rating=3, correct=True, answered_at=at))
    await db_session.flush()


async def one_item(db_session):
    chapter = await make_chapter(db_session, await make_module(db_session))
    return await make_item(db_session, chapter)


def done_dates(body) -> list[str]:
    return [d["date"] for d in body["week"]["days"] if d["done"]]


async def test_week_runs_monday_to_sunday_in_berlin(api, db_session):
    client, app = api
    app.dependency_overrides[get_now] = lambda: berlin(11, 25, 12)
    item = await one_item(db_session)
    await log_review(db_session, item, berlin(11, 22, 23, 59))
    await log_review(db_session, item, berlin(11, 23, 0, 10))
    await log_review(db_session, item, berlin(11, 29, 23, 30))
    await log_review(db_session, item, berlin(11, 30, 0, 10))

    body = (await client.get("/api/progress")).json()

    assert [d["date"] for d in body["week"]["days"]] == [f"2026-11-{d}" for d in range(23, 30)]
    assert done_dates(body) == ["2026-11-23", "2026-11-29"]
    assert body["week"]["done_count"] == 2
    assert body["week"]["goal"] == 4


async def test_several_reviews_on_one_day_count_once(api, db_session):
    client, app = api
    app.dependency_overrides[get_now] = lambda: berlin(11, 25, 12)
    item = await one_item(db_session)
    for hour in (8, 9, 20):
        await log_review(db_session, item, berlin(11, 24, hour))

    body = (await client.get("/api/progress")).json()

    assert body["week"]["done_count"] == 1


async def test_week_across_the_autumn_dst_change(api, db_session):
    client, app = api
    app.dependency_overrides[get_now] = lambda: berlin(10, 26, 12)
    item = await one_item(db_session)
    await log_review(db_session, item, berlin(10, 25, 0, 30))
    await log_review(db_session, item, berlin(10, 25, 23, 30))
    await log_review(db_session, item, berlin(10, 26, 0, 30))
    await log_review(db_session, item, berlin(10, 24, 23, 30))

    body = (await client.get("/api/progress")).json()

    assert body["week"]["days"][0]["date"] == "2026-10-26"
    assert done_dates(body) == ["2026-10-26"]

    app.dependency_overrides[get_now] = lambda: berlin(10, 25, 12)
    body = (await client.get("/api/progress")).json()

    assert body["week"]["days"][0]["date"] == "2026-10-19"
    assert done_dates(body) == ["2026-10-24", "2026-10-25"]


async def test_introduced_excludes_skipped_chapters(api, db_session):
    client, app = api
    now = berlin(11, 25, 12)
    app.dependency_overrides[get_now] = lambda: now
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    await make_chapter(db_session, module, 0, introduced_at=now)
    await make_chapter(db_session, module, 1)
    await make_chapter(db_session, module, 2)
    await make_chapter(db_session, module, 3, status=ChapterStatus.skipped)
    empty = await make_subject(db_session, "Beta")
    await make_subject(db_session, "Gamma", modules=(await make_module(db_session, 1),))

    body = (await client.get("/api/progress")).json()

    by_id = {s["subject_id"]: s for s in body["subjects"]}
    assert by_id[subject.id]["introduced"] == 0.333
    assert by_id[empty.id] == {"subject_id": empty.id, "introduced": 0.0, "solid": 0.0}
    assert len(by_id) == 3


async def test_solid_counts_active_items_of_ready_chapters_with_recall_at_now(api, db_session):
    client, app = api
    now = berlin(11, 25, 12)
    app.dependency_overrides[get_now] = lambda: now
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    ready = await make_chapter(db_session, module, 0, introduced_at=now)
    pending = await make_chapter(db_session, module, 1, status=ChapterStatus.pending)
    # Stability 10 and last review 10 days before due: recall is 0.9 at due and falls after.
    await make_item(db_session, ready, due=now - timedelta(days=1))
    await make_item(db_session, ready, due=now + timedelta(days=10))
    await make_item(db_session, ready)
    await make_item(db_session, pending, due=now - timedelta(days=1))
    other = await make_subject(db_session, "Beta", modules=(await make_module(db_session, 1),))

    body = (await client.get("/api/progress")).json()

    by_id = {s["subject_id"]: s for s in body["subjects"]}
    assert by_id[subject.id]["solid"] == 0.333
    assert by_id[other.id]["solid"] == 0.0
