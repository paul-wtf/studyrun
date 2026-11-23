import itertools
import random
from datetime import UTC, datetime, timedelta

import fsrs.scheduler
from fsrs import Rating, State
from helpers import make_chapter, make_item, make_module
from sqlalchemy import func, select

from studyrun.ai.clock import local_day_bounds
from studyrun.config import Settings
from studyrun.models.db import Chapter, ChapterStatus, Item, ItemKind, ItemStatus, ReviewState
from studyrun.study.assemble import build_run
from studyrun.study.scheduling import record_review

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=30)


def item_ids(entries):
    return [e["item_id"] for e in entries if e["type"] == "item"]


async def test_empty_library_gives_empty_run(db_session):
    assert await build_run(db_session, Settings(), NOW) == []


async def test_reviews_capped_after_long_break(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    kinds = [ItemKind.mc, ItemKind.true_false, ItemKind.cloze]
    items = [
        await make_item(db_session, chapter, kinds[i % 3], due=LONG_AGO + timedelta(minutes=i))
        for i in range(200)
    ]
    for kind in [*kinds, ItemKind.free]:
        await make_item(db_session, chapter, kind)
    settings = Settings()

    entries = await build_run(db_session, settings, NOW)
    assert set(item_ids(entries)) == {i.id for i in items[:8]}

    async def backlog(at):
        return await db_session.scalar(
            select(func.count()).select_from(ReviewState).where(ReviewState.due <= at)
        )

    now = NOW
    counts = [await backlog(now)]
    for _ in range(3):
        entries = await build_run(db_session, settings, now)
        assert len(item_ids(entries)) <= 8
        for item_id in item_ids(entries):
            await record_review(db_session, item_id, Rating.Good, now, correct=True, score=None)
        now += timedelta(days=1)
        counts.append(await backlog(now))
    assert counts[0] > counts[1] > counts[2] > counts[3]


async def test_no_new_items_or_intro_while_reviews_pile_up(db_session):
    module = await make_module(db_session)
    seen = await make_chapter(db_session, module, 0, introduced_at=LONG_AGO)
    later = await make_chapter(db_session, module, 1)
    due = [
        await make_item(db_session, seen, ItemKind.mc, due=LONG_AGO + timedelta(minutes=i))
        for i in range(200)
    ]
    for kind in (ItemKind.true_false, ItemKind.cloze, ItemKind.free):
        await make_item(db_session, seen, kind)
        await make_item(db_session, later, kind)

    entries = await build_run(db_session, Settings(), NOW)
    assert all(e["type"] == "item" for e in entries)
    assert set(item_ids(entries)) == {i.id for i in due[:8]}


async def test_new_items_resume_once_the_backlog_fits_a_run(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    due = [await make_item(db_session, chapter, ItemKind.mc, due=LONG_AGO) for _ in range(8)]
    new = await make_item(db_session, chapter, ItemKind.true_false)

    ids = item_ids(await build_run(db_session, Settings(), NOW))
    assert set(ids) == {i.id for i in due} | {new.id}


async def test_learning_cards_come_before_overdue_reviews(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    await make_item(db_session, chapter, ItemKind.mc, due=NOW - timedelta(weeks=3))
    learning = await make_item(
        db_session, chapter, ItemKind.mc, due=NOW + timedelta(hours=2), state=State.Learning
    )
    relearning = await make_item(
        db_session, chapter, ItemKind.mc, due=NOW + timedelta(hours=1), state=State.Relearning
    )
    tomorrow = await make_item(
        db_session, chapter, ItemKind.mc, due=NOW + timedelta(days=1), state=State.Learning
    )

    settings = Settings(run_review_cap=2, run_new_items=0)
    ids = item_ids(await build_run(db_session, settings, NOW))
    assert set(ids) == {relearning.id, learning.id}
    assert tomorrow.id not in ids


async def test_daily_study_keeps_the_backlog_bounded(db_session, monkeypatch):
    monkeypatch.setattr(fsrs.scheduler, "random", random.Random(0).random)
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    kinds = [ItemKind.mc, ItemKind.true_false, ItemKind.cloze, ItemKind.free]
    for i in range(200):
        await make_item(db_session, chapter, kinds[i % 4])
    settings = Settings()

    async def due_by_tomorrow(at):
        _, today_end = local_day_bounds(at, settings.timezone)
        _, tomorrow_end = local_day_bounds(today_end + timedelta(hours=12), settings.timezone)
        return await db_session.scalar(
            select(func.count())
            .select_from(ReviewState)
            .join(Item, Item.id == ReviewState.item_id)
            .join(Chapter, Chapter.id == Item.chapter_id)
            .where(Item.status == ItemStatus.active, ReviewState.due < tomorrow_end)
        )

    now = NOW
    answers = itertools.count()
    backlog = []
    for _ in range(30):
        for item_id in item_ids(await build_run(db_session, settings, now)):
            rating = Rating.Again if next(answers) % 4 == 0 else Rating.Good
            await record_review(db_session, item_id, rating, now, correct=None, score=None)
        backlog.append(await due_by_tomorrow(now))
        now += timedelta(days=1)
    assert max(backlog) <= 2 * settings.run_review_cap, backlog


async def test_intro_before_new_chapter_items(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module)
    items = [await make_item(db_session, chapter, ItemKind.mc) for _ in range(6)]

    entries = await build_run(db_session, Settings(), NOW)
    assert entries[0] == {"type": "intro", "chapter_id": chapter.id}
    assert item_ids(entries) == [i.id for i in items[:4]]


async def test_items_of_unintroduced_chapter_only_after_intro(db_session):
    module = await make_module(db_session)
    intro = await make_chapter(db_session, module, 0, introduced_at=LONG_AGO)
    later = await make_chapter(db_session, module, 1)
    seen = [await make_item(db_session, intro, ItemKind.mc) for _ in range(2)]
    hidden = [await make_item(db_session, later, ItemKind.true_false) for _ in range(5)]

    entries = await build_run(db_session, Settings(), NOW)
    ids = item_ids(entries)
    assert {i.id for i in seen} <= set(ids)
    assert len(ids) == 4
    pos = entries.index({"type": "intro", "chapter_id": later.id})
    assert entries[pos + 1] == {"type": "item", "item_id": entries[pos + 1]["item_id"]}
    assert entries[pos + 1]["item_id"] in {i.id for i in hidden}
    assert all(
        e["item_id"] not in {i.id for i in hidden} for e in entries[:pos] if e["type"] == "item"
    )

    done = await make_chapter(db_session, module, 2, introduced_at=LONG_AGO)
    await make_item(db_session, done, ItemKind.cloze)
    later.introduced_at = LONG_AGO
    await db_session.flush()
    entries = await build_run(db_session, Settings(), NOW)
    assert all(e["type"] == "item" for e in entries)


async def test_one_free_item_included(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    for _ in range(6):
        await make_item(db_session, chapter, ItemKind.mc)
    free = await make_item(db_session, chapter, ItemKind.free)

    entries = await build_run(db_session, Settings(), NOW)
    assert len(item_ids(entries)) == 5
    assert free.id in item_ids(entries)


async def test_due_free_item_preferred_over_unseen(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    for i in range(8):
        await make_item(db_session, chapter, ItemKind.mc, due=LONG_AGO + timedelta(minutes=i))
    due_free = await make_item(db_session, chapter, ItemKind.free, due=NOW - timedelta(days=1))
    await make_item(db_session, chapter, ItemKind.free)

    entries = await build_run(db_session, Settings(run_new_items=0), NOW)
    assert due_free.id in item_ids(entries)
    assert len(item_ids(entries)) == 9


async def test_no_consecutive_same_kind(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    due = LONG_AGO
    mcs = [await make_item(db_session, chapter, ItemKind.mc, due=due) for _ in range(4)]
    tfs = [await make_item(db_session, chapter, ItemKind.true_false, due=due) for _ in range(4)]

    ids = item_ids(await build_run(db_session, Settings(), NOW))
    kind = {i.id: i.kind for i in mcs + tfs}
    assert len(ids) == 8
    assert all(kind[a] != kind[b] for a, b in itertools.pairwise(ids))


async def test_flagged_deleted_and_failed_excluded(db_session):
    module = await make_module(db_session)
    ready = await make_chapter(db_session, module, 0, introduced_at=LONG_AGO)
    failed = await make_chapter(
        db_session, module, 1, status=ChapterStatus.failed, introduced_at=LONG_AGO
    )
    pending = await make_chapter(db_session, module, 2, status=ChapterStatus.pending)
    good = await make_item(db_session, ready, ItemKind.mc, due=LONG_AGO)
    await make_item(db_session, ready, ItemKind.mc, status=ItemStatus.flagged, due=LONG_AGO)
    await make_item(db_session, ready, ItemKind.mc, status=ItemStatus.deleted)
    await make_item(db_session, failed, ItemKind.mc, due=LONG_AGO)
    await make_item(db_session, failed, ItemKind.mc)
    await make_item(db_session, pending, ItemKind.mc)

    entries = await build_run(db_session, Settings(), NOW)
    assert entries == [{"type": "item", "item_id": good.id}]


async def test_focus_module_follows_position(db_session):
    first = await make_module(db_session, 0)
    second = await make_module(db_session, 1)
    c1 = await make_chapter(db_session, first, 0, introduced_at=LONG_AGO)
    c2 = await make_chapter(db_session, second, 0, introduced_at=LONG_AGO)
    i1 = await make_item(db_session, c1, ItemKind.mc)
    i2 = await make_item(db_session, c2, ItemKind.true_false)

    assert item_ids(await build_run(db_session, Settings(), NOW)) == [i1.id]

    await record_review(db_session, i1.id, Rating.Easy, NOW, correct=True, score=None)
    assert item_ids(await build_run(db_session, Settings(), NOW)) == [i2.id]
