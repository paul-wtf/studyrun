from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from helpers import make_chapter, make_item, make_module, make_subject
from sqlalchemy import select

from studyrun.models.db import ChapterStatus, Item, ItemKind, ItemStatus
from studyrun.study.mock import (
    MINUTES,
    chapter_shares,
    is_unlocked,
    mock_score,
    normalize_answer,
    select_mock_items,
)

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=30)


@pytest.mark.parametrize(
    ("introduced", "total", "unlocked"),
    [(79, 100, False), (80, 100, True), (4, 5, True), (3, 4, False), (0, 0, False)],
)
def test_unlock_threshold(introduced, total, unlocked):
    assert is_unlocked(introduced, total) is unlocked


async def test_shares_exclude_skipped_chapters(db_session):
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    for index in range(4):
        await make_chapter(db_session, module, index, introduced_at=LONG_AGO)
    await make_chapter(db_session, module, 4, status=ChapterStatus.pending)
    await make_chapter(db_session, module, 5, status=ChapterStatus.skipped)
    empty = await make_subject(db_session, "Leer")

    shares = await chapter_shares(db_session, [subject.id, empty.id])

    assert shares[subject.id] == (4, 5)
    assert shares[empty.id] == (0, 0)


async def _kinds(db_session, chapter, counts):
    items = []
    for kind, count in counts.items():
        for _ in range(count):
            items.append(await make_item(db_session, chapter, kind, payload={}))
    return items


def _minutes(kinds_by_id, ids):
    return sum(MINUTES[kinds_by_id[i]] for i in ids)


async def test_selection_fits_the_duration_and_spans_chapters(db_session):
    module = await make_module(db_session)
    other = await make_module(db_session, 1)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    counts = {ItemKind.mc: 4, ItemKind.true_false: 4, ItemKind.cloze: 3, ItemKind.free: 2}
    pool = []
    chapters = []
    for index in range(3):
        chapter = await make_chapter(db_session, module, index, introduced_at=LONG_AGO)
        chapters.append(chapter)
        pool += await _kinds(db_session, chapter, counts)
    unintroduced = await make_chapter(db_session, module, 3)
    hidden = await _kinds(db_session, unintroduced, {ItemKind.true_false: 5})
    foreign = await make_chapter(db_session, other, 0, introduced_at=LONG_AGO)
    hidden += await _kinds(db_session, foreign, {ItemKind.true_false: 5})
    hidden.append(
        await make_item(db_session, chapters[0], ItemKind.true_false, status=ItemStatus.deleted)
    )
    kinds_by_id = {i.id: i.kind for i in pool}

    ids = await select_mock_items(db_session, subject.id, 30, now=NOW, seed=1)

    assert len(ids) == len(set(ids))
    assert set(ids) <= set(kinds_by_id)
    assert not set(ids) & {i.id for i in hidden}
    assert 26 < _minutes(kinds_by_id, ids) <= 27
    by_chapter = {i.id: i.chapter_id for i in pool}
    assert {by_chapter[i] for i in ids} == {c.id for c in chapters}


async def test_selection_is_deterministic_for_a_seed(db_session):
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    for index in range(3):
        chapter = await make_chapter(db_session, module, index, introduced_at=LONG_AGO)
        await _kinds(db_session, chapter, {ItemKind.mc: 5, ItemKind.true_false: 5})

    first = await select_mock_items(db_session, subject.id, 20, now=NOW, seed=7)

    assert await select_mock_items(db_session, subject.id, 20, now=NOW, seed=7) == first
    seeds = [await select_mock_items(db_session, subject.id, 20, now=NOW, seed=s) for s in range(5)]
    assert len({tuple(s) for s in seeds}) > 1


async def test_selection_leans_towards_weak_chapters(db_session):
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    strong = await make_chapter(db_session, module, 0, introduced_at=LONG_AGO)
    weak = await make_chapter(db_session, module, 1, introduced_at=LONG_AGO)
    for _ in range(20):
        await make_item(db_session, strong, ItemKind.true_false, due=NOW + timedelta(days=10))
    for _ in range(20):
        await make_item(db_session, weak, ItemKind.true_false)
    counts: Counter[str] = Counter()
    for seed in range(10):
        ids = await select_mock_items(db_session, subject.id, 10, now=NOW, seed=seed)
        assert len(ids) == 9
        picked = await _chapters_of(db_session, ids)
        assert strong.id in picked and weak.id in picked
        counts["strong"] += picked.count(strong.id)
        counts["weak"] += picked.count(weak.id)

    assert counts["weak"] > 3 * counts["strong"]


async def _chapters_of(db_session, ids):
    rows = dict((await db_session.execute(select(Item.id, Item.chapter_id))).all())
    return [rows[i] for i in ids]


async def test_short_exam_takes_what_fits(db_session):
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    chapter = await make_chapter(db_session, module, introduced_at=LONG_AGO)
    free = await make_item(db_session, chapter, ItemKind.free)
    tf = await make_item(db_session, chapter, ItemKind.true_false)

    assert await select_mock_items(db_session, subject.id, 2, now=NOW, seed=0) == [tf.id]
    assert set(await select_mock_items(db_session, subject.id, 90, now=NOW, seed=0)) == {
        free.id,
        tf.id,
    }


def test_answers_are_normalized_per_kind():
    assert normalize_answer(ItemKind.mc, 3, {"choice": 2}) == {"choice": 2}
    assert normalize_answer(ItemKind.true_false, None, {"value": False}) == {"value": False}
    assert normalize_answer(ItemKind.cloze, None, {"text": " 42 "}) == {"text": " 42 "}
    assert normalize_answer(ItemKind.free, None, {"text": "  "}) is None
    for kind, options, answer in [
        (ItemKind.mc, 3, {"choice": 3}),
        (ItemKind.mc, 3, {"choice": True}),
        (ItemKind.true_false, None, {"value": 1}),
        (ItemKind.free, None, {"text": 5}),
    ]:
        with pytest.raises(ValueError):
            normalize_answer(kind, options, answer)


def test_score_counts_unanswered_and_ungraded_as_zero():
    entries = [
        {"chapter_id": 1, "score": 100},
        {"chapter_id": 1, "score": 0},
        {"chapter_id": 2, "score": 85},
        {"chapter_id": 2, "score": None},
    ]
    assert mock_score(entries) == 46
    assert mock_score([]) == 0
