from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.llm import LLM, LLMUnavailable
from studyrun.models.db import (
    Booklet,
    Chapter,
    ChapterStatus,
    Item,
    ItemKind,
    ItemStatus,
    MockExam,
    Module,
    ReviewState,
)
from studyrun.study.answers import check_objective
from studyrun.study.grading import grade_free
from studyrun.study.scheduling import (
    rating_for_objective,
    rating_for_score,
    record_review,
    retrievability,
)

MINUTES: dict[ItemKind, float] = {
    ItemKind.mc: 1.5,
    ItemKind.true_false: 1.0,
    ItemKind.cloze: 2.0,
    ItemKind.free: 6.0,
}
FILL = 0.9
UNLOCK_SHARE = 0.8
# Keeps a chapter recalled perfectly today in the draw, just rarely.
MIN_WEIGHT = 0.05

MockEntry = dict[str, Any]


def is_unlocked(introduced: int, total: int) -> bool:
    return total > 0 and introduced / total >= UNLOCK_SHARE


async def chapter_shares(
    session: AsyncSession, subject_ids: Sequence[int]
) -> dict[int, tuple[int, int]]:
    shares = {subject_id: (0, 0) for subject_id in subject_ids}
    rows = await session.execute(
        select(Module.subject_id, func.count(Chapter.introduced_at), func.count(Chapter.id))
        .join(Booklet, Booklet.module_id == Module.id)
        .join(Chapter, Chapter.booklet_id == Booklet.id)
        .where(Module.subject_id.in_(subject_ids), Chapter.status != ChapterStatus.skipped)
        .group_by(Module.subject_id)
    )
    for subject_id, introduced, total in rows:
        if subject_id is not None:
            shares[subject_id] = (introduced, total)
    return shares


@dataclass(frozen=True)
class _Candidate:
    item_id: int
    chapter_id: int
    kind: ItemKind
    weakness: float


async def _candidates(
    session: AsyncSession, subject_id: int, now: datetime, blocked: frozenset[int]
) -> list[_Candidate]:
    stmt = (
        select(Item.id, Item.chapter_id, Item.kind, ReviewState.card)
        .join(Chapter, Chapter.id == Item.chapter_id)
        .join(Booklet, Booklet.id == Chapter.booklet_id)
        .join(Module, Module.id == Booklet.module_id)
        .outerjoin(ReviewState, ReviewState.item_id == Item.id)
        .where(
            Module.subject_id == subject_id,
            Item.status == ItemStatus.active,
            Chapter.status == ChapterStatus.ready,
            Chapter.introduced_at.is_not(None),
        )
        .order_by(Module.position, Module.id, Chapter.index, Chapter.id, Item.id)
    )
    if blocked:
        stmt = stmt.where(Item.id.not_in(blocked))
    rows = await session.execute(stmt)
    candidates = []
    for item_id, chapter_id, kind, card in rows:
        candidates.append(_Candidate(item_id, chapter_id, kind, 1.0 - retrievability(card, now)))
    return candidates


async def select_mock_items(
    session: AsyncSession,
    subject_id: int,
    duration_minutes: int,
    *,
    now: datetime,
    seed: int,
    blocked: frozenset[int] = frozenset(),
) -> list[int]:
    candidates = await _candidates(session, subject_id, now, blocked)
    pools: dict[int, list[_Candidate]] = {}
    for candidate in candidates:
        pools.setdefault(candidate.chapter_id, []).append(candidate)
    weights = {
        chapter_id: max(MIN_WEIGHT, sum(c.weakness for c in pool) / len(pool))
        for chapter_id, pool in pools.items()
    }
    rng = random.Random(seed)
    remaining = FILL * duration_minutes
    chosen: list[_Candidate] = []

    def fitting(chapter_id: int) -> list[_Candidate]:
        return [c for c in pools[chapter_id] if MINUTES[c.kind] <= remaining]

    def take(chapter_id: int, *, cheapest: bool = False) -> None:
        nonlocal remaining
        options = fitting(chapter_id)
        if not options:
            return
        if cheapest:
            least = min(MINUTES[c.kind] for c in options)
            options = [c for c in options if MINUTES[c.kind] == least]
        pick = rng.choices(options, weights=[MIN_WEIGHT + c.weakness for c in options])[0]
        pools[chapter_id].remove(pick)
        chosen.append(pick)
        remaining -= MINUTES[pick.kind]

    for chapter_id in sorted(pools, key=lambda c: -weights[c]):
        take(chapter_id, cheapest=True)
    while open_chapters := [c for c in pools if fitting(c)]:
        take(rng.choices(open_chapters, weights=[weights[c] for c in open_chapters])[0])

    position = {c.item_id: i for i, c in enumerate(candidates)}
    return sorted((c.item_id for c in chosen), key=position.__getitem__)


def normalize_answer(
    kind: ItemKind, options: int | None, answer: dict[str, Any]
) -> dict[str, Any] | None:
    if kind == ItemKind.mc:
        choice = answer.get("choice")
        if not isinstance(choice, int) or isinstance(choice, bool):
            raise ValueError("choice must be an integer")
        if not 0 <= choice < (options or 0):
            raise ValueError("choice is not an option")
        return {"choice": choice}
    if kind == ItemKind.true_false:
        value = answer.get("value")
        if not isinstance(value, bool):
            raise ValueError("value must be a boolean")
        return {"value": value}
    text = answer.get("text")
    if isinstance(text, str):
        return {"text": text} if text.strip() else None
    raise ValueError("text must be a string")


def _mean(scores: Sequence[int | None]) -> int:
    if not scores:
        return 0
    total = sum(s or 0 for s in scores)
    return (2 * total + len(scores)) // (2 * len(scores))


def mock_score(entries: Sequence[MockEntry]) -> int:
    return _mean([e.get("score") for e in entries])


def chapter_scores(entries: Sequence[MockEntry]) -> list[tuple[int, int, int]]:
    by_chapter: dict[int, list[int | None]] = {}
    for entry in entries:
        by_chapter.setdefault(entry["chapter_id"], []).append(entry.get("score"))
    return [(chapter_id, len(scores), _mean(scores)) for chapter_id, scores in by_chapter.items()]


def pending_self_rating(entries: Sequence[MockEntry]) -> int:
    return sum(1 for e in entries if e.get("grading_unavailable") and e.get("score") is None)


def rescore(mock: MockExam) -> None:
    mock.score = mock_score(mock.entries)
    mock.passed = mock.score >= mock.pass_mark


def finish_started(mock: MockExam) -> bool:
    return mock.finished_at is None and any(e.get("checked") for e in mock.entries)


async def _locked(session: AsyncSession, mock_id: int) -> MockExam:
    return (
        await session.scalars(
            select(MockExam)
            .where(MockExam.id == mock_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()


async def finish_mock(session: AsyncSession, llm: LLM, mock_id: int, now: datetime) -> MockExam:
    """Commits after every graded free answer, so a retry after a crash pays only for the
    answers still ungraded."""
    grading = True
    items: dict[int, Item] = {}
    while True:
        mock = await _locked(session, mock_id)
        if mock.finished_at is not None:
            return mock
        if not items:
            items = {
                item.id: item
                for item in await session.scalars(
                    select(Item).where(Item.id.in_([e["item_id"] for e in mock.entries]))
                )
            }
        entries = list(mock.entries)
        graded = False
        for n, entry in enumerate(entries):
            if entry.get("checked"):
                continue
            item = items[entry["item_id"]]
            answer = entry.get("answer")
            free = item.kind == ItemKind.free
            if graded and grading and free and answer is not None:
                break
            result: MockEntry = {
                "checked": True,
                "score": 0,
                "correct": False,
                "grading_unavailable": False,
                "feedback": None,
                "missing": [],
            }
            if answer is not None and not free:
                correct = check_objective(item, answer).correct
                await record_review(
                    session,
                    item.id,
                    rating_for_objective(correct),
                    now,
                    correct=correct,
                    score=None,
                )
                result |= {"score": 100 if correct else 0, "correct": correct}
            elif answer is not None:
                grade = None
                if grading:
                    try:
                        grade = await grade_free(session, llm, item, answer["text"], now)
                    except (BudgetExceeded, LLMUnavailable):
                        grading = False
                if grade is None:
                    result |= {"score": None, "correct": None, "grading_unavailable": True}
                else:
                    graded = True
                    await record_review(
                        session,
                        item.id,
                        rating_for_score(grade.score),
                        now,
                        correct=None,
                        score=grade.score,
                    )
                    result |= {
                        "score": grade.score,
                        "correct": grade.score >= 75,
                        "feedback": grade.feedback,
                        "missing": grade.missing,
                    }
            entries[n] = {**entry, **result}
        mock.entries = entries
        if all(e.get("checked") for e in entries):
            mock.finished_at = now
            rescore(mock)
        await session.commit()
