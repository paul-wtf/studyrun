from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from fsrs import Rating
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.models.db import Chapter, Item, ItemKind, MockExam, Subject
from studyrun.routes.modules import Session
from studyrun.routes.runs import (
    _ITEM_VIEW,
    AnswerIn,
    ItemViewOut,
    Llm,
    Now,
    SelfRateIn,
    pdf_link,
)
from studyrun.routes.subjects import _get_subject
from studyrun.study.answers import expected_answer, public_view
from studyrun.study.mock import (
    MockEntry,
    chapter_scores,
    chapter_shares,
    finish_mock,
    is_unlocked,
    normalize_answer,
    pending_self_rating,
    rescore,
    select_mock_items,
)
from studyrun.study.scheduling import record_review

router = APIRouter()


class GivenAnswerOut(BaseModel):
    choice: int | None = None
    value: bool | None = None
    text: str | None = None


class MockReviewOut(BaseModel):
    score: int | None
    correct: bool | None
    expected: str | None
    explanation: str | None
    feedback: str | None
    missing: list[str]
    model_answer: str | None
    grading_unavailable: bool


class MockEntryOut(BaseModel):
    n: int
    answered: bool
    answer: GivenAnswerOut | None
    item: ItemViewOut
    review: MockReviewOut | None


class ChapterScoreOut(BaseModel):
    chapter_id: int
    title: str
    items: int
    score: int


class MockResultOut(BaseModel):
    score: int
    passed: bool
    pass_mark: int
    pending_self_rating: int
    chapters: list[ChapterScoreOut]


class MockExamOut(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    started_at: datetime
    deadline: datetime
    finished_at: datetime | None
    finished: bool
    expired: bool
    entries: list[MockEntryOut]
    result: MockResultOut | None


class MockAnswerOut(BaseModel):
    n: int
    answered: bool


class MockSummaryOut(BaseModel):
    id: int
    started_at: datetime
    deadline: datetime
    finished_at: datetime | None
    score: int | None
    passed: bool | None


def _review(item: Item, entry: MockEntry) -> MockReviewOut:
    objective = item.kind != ItemKind.free
    return MockReviewOut(
        score=entry.get("score"),
        correct=entry.get("correct"),
        expected=expected_answer(item) if objective else None,
        explanation=str(item.payload.get("explanation", "")) if objective else None,
        feedback=entry.get("feedback"),
        missing=entry.get("missing", []),
        model_answer=None if objective else item.payload.get("model_answer"),
        grading_unavailable=bool(entry.get("grading_unavailable")),
    )


async def _mock_out(
    session: AsyncSession, mock: MockExam, subject: Subject, now: datetime
) -> MockExamOut:
    items = {
        item.id: (item, booklet_id)
        for item, booklet_id in (
            await session.execute(
                select(Item, Chapter.booklet_id)
                .join(Chapter, Chapter.id == Item.chapter_id)
                .where(Item.id.in_([e["item_id"] for e in mock.entries]))
            )
        ).all()
    }
    finished = mock.finished_at is not None
    entries = []
    for n, entry in enumerate(mock.entries):
        item, booklet_id = items[entry["item_id"]]
        view = public_view(item) | {"source": pdf_link(booklet_id, item.source_page)}
        answer = entry.get("answer")
        entries.append(
            MockEntryOut(
                n=n,
                answered=answer is not None,
                answer=None if answer is None else GivenAnswerOut(**answer),
                item=_ITEM_VIEW.validate_python(view),
                review=_review(item, entry) if finished else None,
            )
        )
    result = None
    if finished and mock.score is not None and mock.passed is not None:
        titles = dict(
            (
                await session.execute(
                    select(Chapter.id, Chapter.title).where(
                        Chapter.id.in_([e["chapter_id"] for e in mock.entries])
                    )
                )
            ).all()
        )
        result = MockResultOut(
            score=mock.score,
            passed=mock.passed,
            pass_mark=subject.pass_mark,
            pending_self_rating=pending_self_rating(mock.entries),
            chapters=[
                ChapterScoreOut(chapter_id=c, title=titles[c], items=count, score=score)
                for c, count, score in chapter_scores(mock.entries)
            ],
        )
    return MockExamOut(
        id=mock.id,
        subject_id=mock.subject_id,
        subject_name=subject.name,
        started_at=mock.started_at,
        deadline=mock.deadline,
        finished_at=mock.finished_at,
        finished=finished,
        expired=not finished and now >= mock.deadline,
        entries=entries,
        result=result,
    )


async def _get_mock(session: AsyncSession, mock_id: int) -> tuple[MockExam, Subject]:
    mock = (
        await session.scalars(select(MockExam).where(MockExam.id == mock_id).with_for_update())
    ).one_or_none()
    if mock is None:
        raise HTTPException(404, "Bosskampf nicht gefunden")
    return mock, await _get_subject(session, mock.subject_id)


def _entry(mock: MockExam, n: int) -> MockEntry:
    if not 0 <= n < len(mock.entries):
        raise HTTPException(404, "Eintrag nicht gefunden")
    return mock.entries[n]


def _store(mock: MockExam, n: int, entry: MockEntry) -> None:
    mock.entries = [entry if i == n else e for i, e in enumerate(mock.entries)]


LOCKED = "Der Bosskampf öffnet, sobald 80 % der Kapitel eingeführt sind."
NO_ITEMS = "Für dieses Fach gibt es noch keine Fragen."


async def _new_mock(session: AsyncSession, subject: Subject, now: datetime) -> MockExam | str:
    introduced, total = (await chapter_shares(session, [subject.id]))[subject.id]
    if not is_unlocked(introduced, total):
        return LOCKED
    ids = await select_mock_items(
        session, subject.id, subject.duration_minutes, now=now, seed=int(now.timestamp())
    )
    if not ids:
        return NO_ITEMS
    chapters = dict(
        (await session.execute(select(Item.id, Item.chapter_id).where(Item.id.in_(ids)))).all()
    )
    mock = MockExam(
        subject_id=subject.id,
        started_at=now,
        deadline=now + timedelta(minutes=subject.duration_minutes),
        entries=[{"item_id": i, "chapter_id": chapters[i], "answer": None} for i in ids],
    )
    session.add(mock)
    await session.flush()
    return mock


@router.post("/subjects/{subject_id}/mock")
async def start_mock(subject_id: int, session: Session, now: Now, llm: Llm) -> MockExamOut:
    subject = await _get_subject(session, subject_id)
    mock = (
        await session.scalars(
            select(MockExam)
            .where(MockExam.subject_id == subject_id, MockExam.finished_at.is_(None))
            .order_by(MockExam.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).first()
    if mock is not None and now - mock.deadline > mock.deadline - mock.started_at:
        await finish_mock(session, llm, mock, subject.pass_mark, now)
        new = await _new_mock(session, subject, now)
        # A 409 here would roll back the grading that was just paid for.
        if isinstance(new, MockExam):
            mock = new
    elif mock is None:
        new = await _new_mock(session, subject, now)
        if not isinstance(new, MockExam):
            raise HTTPException(409, new)
        mock = new
    return await _mock_out(session, mock, subject, now)


@router.get("/mock/{mock_id}")
async def get_mock(mock_id: int, session: Session, now: Now) -> MockExamOut:
    mock, subject = await _get_mock(session, mock_id)
    return await _mock_out(session, mock, subject, now)


@router.post("/mock/{mock_id}/answers/{n}")
async def answer_mock(
    mock_id: int, n: int, body: AnswerIn, session: Session, now: Now
) -> MockAnswerOut:
    mock, _ = await _get_mock(session, mock_id)
    entry = _entry(mock, n)
    if mock.finished_at is not None:
        raise HTTPException(409, "Der Bosskampf ist schon abgegeben.")
    if now >= mock.deadline:
        raise HTTPException(409, "Zeit abgelaufen")
    item = await session.get(Item, entry["item_id"])
    if item is None:
        raise HTTPException(404, "Frage nicht gefunden")
    options = len(item.payload["options"]) if item.kind == ItemKind.mc else None
    try:
        answer: dict[str, Any] | None = normalize_answer(item.kind, options, body.answer)
    except ValueError as exc:
        raise HTTPException(422, "Ungültige Antwort.") from exc
    _store(mock, n, {**entry, "answer": answer})
    await session.flush()
    return MockAnswerOut(n=n, answered=answer is not None)


@router.post("/mock/{mock_id}/finish")
async def finish(mock_id: int, session: Session, now: Now, llm: Llm) -> MockExamOut:
    mock, subject = await _get_mock(session, mock_id)
    if mock.finished_at is None:
        await finish_mock(session, llm, mock, subject.pass_mark, now)
    return await _mock_out(session, mock, subject, now)


@router.post("/mock/{mock_id}/self-rate/{n}")
async def self_rate(
    mock_id: int, n: int, body: SelfRateIn, session: Session, now: Now
) -> MockExamOut:
    mock, subject = await _get_mock(session, mock_id)
    entry = _entry(mock, n)
    if mock.finished_at is None:
        raise HTTPException(409, "Selbst bewerten geht erst nach der Abgabe.")
    if not entry.get("grading_unavailable") or entry.get("score") is not None:
        raise HTTPException(409, "Diese Antwort braucht keine Selbstbewertung.")
    good = body.rating == "good"
    await record_review(
        session,
        entry["item_id"],
        Rating.Good if good else Rating.Again,
        now,
        correct=good,
        score=None,
    )
    _store(mock, n, {**entry, "score": 100 if good else 0, "correct": good})
    rescore(mock, subject.pass_mark)
    await session.flush()
    return await _mock_out(session, mock, subject, now)


@router.get("/subjects/{subject_id}/mocks")
async def list_mocks(subject_id: int, session: Session) -> list[MockSummaryOut]:
    await _get_subject(session, subject_id)
    mocks = await session.scalars(
        select(MockExam).where(MockExam.subject_id == subject_id).order_by(MockExam.id.desc())
    )
    return [
        MockSummaryOut(
            id=m.id,
            started_at=m.started_at,
            deadline=m.deadline,
            finished_at=m.finished_at,
            score=m.score,
            passed=m.passed,
        )
        for m in mocks
    ]
