from datetime import UTC, datetime, timedelta

import pytest

from studyrun.config import Settings
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Item, ItemKind, Module, ReviewLog
from studyrun.planning.pace import measured_pace

NOW = datetime(2026, 11, 24, 9, tzinfo=UTC)
WINDOW_START = datetime(2026, 10, 27, 23, tzinfo=UTC)


@pytest.fixture
async def chapter(db_session):
    module = Module(name="Modul", position=0)
    db_session.add(module)
    await db_session.flush()
    booklet = Booklet(module_id=module.id, filename="b.pdf", pdf=b"", page_count=10)
    db_session.add(booklet)
    await db_session.flush()
    chapter = Chapter(
        booklet_id=booklet.id,
        index=0,
        title="Kapitel",
        first_page=1,
        last_page=10,
        status=ChapterStatus.ready,
    )
    db_session.add(chapter)
    await db_session.flush()
    return chapter


async def answer(session, chapter, *times, item=None):
    if item is None:
        item = Item(chapter_id=chapter.id, kind=ItemKind.mc, payload={}, source_page=1)
        session.add(item)
        await session.flush()
    for at in times:
        session.add(ReviewLog(item_id=item.id, rating=3, correct=True, answered_at=at))
    await session.flush()
    return item


def day(n, hour=8):
    return datetime(2026, 11, 24 - n, hour, tzinfo=UTC)


async def test_falls_back_with_fewer_than_seven_study_days(db_session, chapter):
    for n in range(6):
        for _ in range(5):
            await answer(db_session, chapter, day(n))
    assert await measured_pace(db_session, Settings(run_new_items=4), NOW) == 4.0


async def test_new_items_per_day_over_28_days(db_session, chapter):
    for n in range(7):
        await answer(db_session, chapter, day(n), day(n) + timedelta(hours=1))
    old = await answer(db_session, chapter, WINDOW_START - timedelta(minutes=30))
    await answer(db_session, chapter, day(10), item=old)
    await answer(db_session, chapter, WINDOW_START)
    await answer(db_session, chapter, NOW + timedelta(hours=1))

    assert await measured_pace(db_session, Settings(), NOW) == pytest.approx(9 / 28)


async def test_study_days_are_berlin_days(db_session, chapter):
    for n in range(6):
        await answer(db_session, chapter, day(n + 1))
    await answer(db_session, chapter, datetime(2026, 11, 23, 23, 30, tzinfo=UTC))

    assert await measured_pace(db_session, Settings(), NOW) == pytest.approx(7 / 28)


async def test_falls_back_when_nothing_new_was_learned(db_session, chapter):
    old = await answer(db_session, chapter, WINDOW_START - timedelta(days=3))
    for n in range(8):
        await answer(db_session, chapter, day(n), item=old)
    assert await measured_pace(db_session, Settings(run_new_items=3), NOW) == 3.0


async def test_fallback_is_never_zero(db_session, chapter):
    assert await measured_pace(db_session, Settings(run_new_items=0), NOW) == 1.0
