import itertools
import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import fsrs.scheduler
import pytest
from fsrs import Rating, State
from helpers import make_chapter, make_item, make_module, make_subject
from sqlalchemy import func, select

from studyrun.ai.clock import local_day_bounds
from studyrun.config import Settings
from studyrun.models.db import (
    AttemptStatus,
    Chapter,
    ChapterStatus,
    Item,
    ItemKind,
    ItemStatus,
    ReviewState,
    Semester,
)
from studyrun.study.assemble import build_run
from studyrun.study.scheduling import record_review

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=30)
TODAY = date(2026, 11, 23)
BERLIN = ZoneInfo("Europe/Berlin")


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


@pytest.mark.parametrize("seed", [0, 1, 2])
async def test_daily_study_keeps_the_backlog_bounded(db_session, monkeypatch, seed):
    monkeypatch.setattr(fsrs.scheduler, "random", random.Random(seed).random)
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
    seen = []
    for _ in range(30):
        for item_id in item_ids(await build_run(db_session, settings, now)):
            rating = Rating.Again if next(answers) % 4 == 0 else Rating.Good
            await record_review(db_session, item_id, rating, now, correct=None, score=None)
        backlog.append(await due_by_tomorrow(now))
        seen.append(await db_session.scalar(select(func.count()).select_from(ReviewState)))
        now += timedelta(days=1)
    assert max(backlog[-10:]) <= max(backlog[:10]) + settings.run_review_cap // 2, backlog
    assert seen[9] < seen[19] < seen[29], seen


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


async def test_new_items_rotate_through_kinds(db_session):
    module = await make_module(db_session)
    first = await make_chapter(db_session, module, 0, introduced_at=LONG_AGO)
    second = await make_chapter(db_session, module, 1, introduced_at=LONG_AGO)
    mcs = [await make_item(db_session, first, ItemKind.mc) for _ in range(4)]
    tfs = [await make_item(db_session, first, ItemKind.true_false) for _ in range(2)]
    cloze = await make_item(db_session, first, ItemKind.cloze)
    await make_item(db_session, second, ItemKind.true_false)

    ids = item_ids(await build_run(db_session, Settings(run_new_items=5), NOW))
    assert set(ids) == {mcs[0].id, tfs[0].id, cloze.id, mcs[1].id, tfs[1].id}


async def test_one_free_item_included(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    for _ in range(6):
        await make_item(db_session, chapter, ItemKind.mc)
    free = await make_item(db_session, chapter, ItemKind.free)

    ids = item_ids(await build_run(db_session, Settings(), NOW))
    assert free.id in ids
    assert len(ids) == 4

    ids = item_ids(await build_run(db_session, Settings(run_new_items=1), NOW))
    assert free.id in ids
    assert len(ids) == 2


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


async def learn(db_session, ids):
    for item_id in ids:
        await record_review(db_session, item_id, Rating.Easy, NOW, correct=True, score=None)


async def test_focus_follows_the_plan_order(db_session):
    late = await make_module(db_session, 0)
    soon = await make_module(db_session, 1)
    late_chapter = await make_chapter(db_session, late, 0, introduced_at=LONG_AGO)
    soon_chapter = await make_chapter(db_session, soon, 0, introduced_at=LONG_AGO)
    soon_next = await make_chapter(db_session, soon, 1)
    late_items = [await make_item(db_session, late_chapter, ItemKind.mc) for _ in range(2)]
    soon_items = [await make_item(db_session, soon_chapter, ItemKind.mc) for _ in range(2)]
    fresh = await make_item(db_session, soon_next, ItemKind.mc)
    await make_subject(db_session, "Später", sitting=date(2027, 3, 10), modules=(late,))
    await make_subject(db_session, "Früher", sitting=date(2027, 2, 10), modules=(soon,))

    entries = await build_run(db_session, Settings(), NOW)
    assert set(item_ids(entries)) == {i.id for i in soon_items} | {fresh.id}
    assert {"type": "intro", "chapter_id": soon_next.id} in entries

    await learn(db_session, item_ids(entries))
    soon_next.introduced_at = NOW
    await db_session.flush()
    assert set(item_ids(await build_run(db_session, Settings(), NOW))) == {i.id for i in late_items}


async def test_unassigned_modules_come_after_planned_subjects(db_session):
    loose = await make_module(db_session, 0)
    planned = await make_module(db_session, 1)
    loose_item = await make_item(
        db_session, await make_chapter(db_session, loose, introduced_at=LONG_AGO), ItemKind.mc
    )
    planned_item = await make_item(
        db_session, await make_chapter(db_session, planned, introduced_at=LONG_AGO), ItemKind.mc
    )
    await make_subject(db_session, "Fach", sitting=date(2027, 2, 10), modules=(planned,))

    assert item_ids(await build_run(db_session, Settings(), NOW)) == [planned_item.id]
    await learn(db_session, [planned_item.id])
    assert item_ids(await build_run(db_session, Settings(), NOW)) == [loose_item.id]


async def test_passed_subject_is_no_focus(db_session):
    done = await make_module(db_session, 0)
    loose = await make_module(db_session, 1)
    await make_item(
        db_session, await make_chapter(db_session, done, introduced_at=LONG_AGO), ItemKind.mc
    )
    loose_item = await make_item(
        db_session, await make_chapter(db_session, loose, introduced_at=LONG_AGO), ItemKind.mc
    )
    await make_subject(
        db_session,
        "Bestanden",
        sitting=date(2026, 10, 1),
        status=AttemptStatus.passed,
        modules=(done,),
    )

    assert item_ids(await build_run(db_session, Settings(), NOW)) == [loose_item.id]


@pytest.mark.parametrize(("days", "pulled"), [(21, True), (22, False), (-1, False)])
async def test_pull_forward_only_inside_21_days(db_session, days, pulled):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    item = await make_item(db_session, chapter, ItemKind.mc, due=NOW + timedelta(days=1))
    await make_subject(db_session, "Fach", sitting=TODAY + timedelta(days=days), modules=(module,))

    assert item_ids(await build_run(db_session, Settings(), NOW)) == ([item.id] if pulled else [])


def on(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=BERLIN).astimezone(UTC)


async def test_pull_forward_fills_reviews_up_to_the_cap(db_session):
    near = await make_module(db_session, 0)
    far = await make_module(db_session, 1)
    loose = await make_module(db_session, 2)
    chapter = await make_chapter(db_session, near, introduced_at=LONG_AGO)
    far_chapter = await make_chapter(db_session, far, introduced_at=LONG_AGO)
    loose_chapter = await make_chapter(db_session, loose, introduced_at=LONG_AGO)
    sitting = TODAY + timedelta(days=10)
    due = [await make_item(db_session, chapter, ItemKind.mc, due=LONG_AGO) for _ in range(2)]
    ahead = {
        offset: await make_item(
            db_session, chapter, ItemKind.true_false, due=on(TODAY + timedelta(days=offset))
        )
        for offset in (10, 3, 11, 1)
    }
    others = [
        await make_item(db_session, far_chapter, ItemKind.mc, due=on(TODAY + timedelta(days=1))),
        await make_item(db_session, loose_chapter, ItemKind.mc, due=on(TODAY + timedelta(days=1))),
    ]
    await make_subject(db_session, "Nah", sitting=sitting, modules=(near,))
    await make_subject(db_session, "Fern", sitting=TODAY + timedelta(days=60), modules=(far,))
    due_ids = {i.id for i in due}

    def pulled(*offsets):
        return due_ids | {ahead[o].id for o in offsets}

    ids = item_ids(await build_run(db_session, Settings(), NOW))
    assert set(ids) == pulled(1, 3, 10)
    assert not {i.id for i in others} & set(ids)
    assert set(item_ids(await build_run(db_session, Settings(run_review_cap=4), NOW))) == (
        pulled(1, 3)
    )
    assert set(item_ids(await build_run(db_session, Settings(run_review_cap=2), NOW))) == (pulled())


async def test_subject_run_takes_only_that_subjects_items(db_session):
    other = await make_module(db_session, 0)
    mine = await make_module(db_session, 1)
    other_chapter = await make_chapter(db_session, other, 0, introduced_at=LONG_AGO)
    my_chapter = await make_chapter(db_session, mine, 0, introduced_at=LONG_AGO)
    my_next = await make_chapter(db_session, mine, 1)
    await make_item(db_session, other_chapter, ItemKind.mc, due=LONG_AGO)
    await make_item(db_session, other_chapter, ItemKind.true_false)
    await make_item(db_session, other_chapter, ItemKind.free)
    my_due = await make_item(db_session, my_chapter, ItemKind.mc, due=LONG_AGO)
    my_new = await make_item(db_session, my_chapter, ItemKind.true_false)
    my_fresh = await make_item(db_session, my_next, ItemKind.cloze)
    subject = await make_subject(db_session, "Fach", modules=(mine,))

    entries = await build_run(db_session, Settings(), NOW, subject_id=subject.id)
    assert set(item_ids(entries)) == {my_due.id, my_new.id, my_fresh.id}
    assert {"type": "intro", "chapter_id": my_next.id} in entries


async def test_subject_run_pulls_forward_when_nothing_is_due(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    items = {
        days: await make_item(db_session, chapter, ItemKind.mc, due=NOW + timedelta(days=days))
        for days in (40, 2, 5)
    }
    subject = await make_subject(db_session, "Fach", modules=(module,))
    settings = Settings(run_review_cap=2)

    assert await build_run(db_session, settings, NOW) == []
    ids = item_ids(await build_run(db_session, settings, NOW, subject_id=subject.id))
    assert set(ids) == {items[2].id, items[5].id}


async def test_subject_run_gate_counts_only_that_subject(db_session):
    other = await make_module(db_session, 0)
    mine = await make_module(db_session, 1)
    other_chapter = await make_chapter(db_session, other, introduced_at=LONG_AGO)
    my_chapter = await make_chapter(db_session, mine, introduced_at=LONG_AGO)
    for i in range(20):
        await make_item(db_session, other_chapter, ItemKind.mc, due=LONG_AGO + timedelta(minutes=i))
    my_new = await make_item(db_session, my_chapter, ItemKind.true_false)
    subject = await make_subject(db_session, "Fach", modules=(mine,))

    assert my_new.id not in item_ids(await build_run(db_session, Settings(), NOW))
    run = await build_run(db_session, Settings(), NOW, subject_id=subject.id)
    assert item_ids(run) == [my_new.id]

    my_due = [await make_item(db_session, my_chapter, ItemKind.mc, due=LONG_AGO) for _ in range(9)]
    run = await build_run(db_session, Settings(), NOW, subject_id=subject.id)
    assert set(item_ids(run)) == {i.id for i in my_due[:8]}


async def module_with_item(db_session, position, kind=ItemKind.mc):
    module = await make_module(db_session, position)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    return module, await make_item(db_session, chapter, kind)


async def test_subjects_outside_the_plan_order_feed_the_daily_run(db_session):
    planned, planned_item = await module_with_item(db_session, 3)
    unplannable, unplannable_item = await module_with_item(db_session, 2)
    later, later_item = await module_with_item(db_session, 1)
    _, loose_item = await module_with_item(db_session, 0)
    await make_subject(db_session, "Geplant", sitting=date(2027, 2, 10), modules=(planned,))
    no_semester = await make_subject(db_session, "Zeta", modules=(unplannable,))
    no_semester.recommended_semester = 5
    await make_subject(db_session, "Alpha", modules=(later,))

    sequence = []
    for _ in range(4):
        ids = item_ids(await build_run(db_session, Settings(), NOW))
        sequence.append(ids)
        await learn(db_session, ids)
    assert sequence == [[planned_item.id], [unplannable_item.id], [later_item.id], [loose_item.id]]


async def test_passed_and_unresolved_subjects_are_no_focus(db_session):
    passed, _ = await module_with_item(db_session, 0)
    unresolved, _ = await module_with_item(db_session, 1)
    await make_subject(
        db_session,
        "Bestanden",
        sitting=date(2026, 10, 1),
        status=AttemptStatus.passed,
        modules=(passed,),
    )
    await make_subject(db_session, "Offen", sitting=date(2026, 11, 1), modules=(unresolved,))

    assert await build_run(db_session, Settings(), NOW) == []


async def test_free_item_fallback_skips_passed_subjects(db_session):
    passed, _ = await module_with_item(db_session, 0, ItemKind.free)
    _, loose_item = await module_with_item(db_session, 1)
    await make_subject(
        db_session,
        "Bestanden",
        sitting=date(2026, 10, 1),
        status=AttemptStatus.passed,
        modules=(passed,),
    )

    assert item_ids(await build_run(db_session, Settings(), NOW)) == [loose_item.id]


async def test_planned_sitting_inside_the_window_pulls_forward(db_session):
    db_session.add(Semester(label="3a", starts_on=date(2026, 4, 1)))
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    item = await make_item(db_session, chapter, ItemKind.mc, due=NOW + timedelta(days=1))
    await make_subject(
        db_session,
        "Fach",
        sitting=TODAY + timedelta(days=21),
        status=AttemptStatus.planned,
        modules=(module,),
    )

    assert item_ids(await build_run(db_session, Settings(), NOW)) == [item.id]
