from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fsrs import Rating
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.clock import local_day_bounds
from studyrun.ai.llm import LLM, LLMUnavailable
from studyrun.config import Settings
from studyrun.content.schemas import Concept
from studyrun.deps import get_llm, get_now, get_settings
from studyrun.models.db import (
    Chapter,
    ChapterStatus,
    Item,
    ItemKind,
    ItemStatus,
    ReviewState,
    Run,
    Subject,
)
from studyrun.routes.modules import Session
from studyrun.study.answers import check_objective, public_view
from studyrun.study.assemble import build_run
from studyrun.study.grading import grade_free
from studyrun.study.scheduling import rating_for_objective, rating_for_score, record_review

router = APIRouter()

Now = Annotated[datetime, Depends(get_now)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Llm = Annotated[LLM, Depends(get_llm)]


class StartRunIn(BaseModel):
    subject_id: int | None = None


class AnswerIn(BaseModel):
    answer: dict[str, Any]


class SelfRateIn(BaseModel):
    rating: Literal["again", "good"]


class McQuestionOut(BaseModel):
    id: int
    kind: Literal["mc"]
    prompt: str
    options: list[str]


class TrueFalseQuestionOut(BaseModel):
    id: int
    kind: Literal["true_false"]
    statement: str


class ClozeQuestionOut(BaseModel):
    id: int
    kind: Literal["cloze"]
    text: str


class FreeQuestionOut(BaseModel):
    id: int
    kind: Literal["free"]
    prompt: str


QuestionOut = Annotated[
    McQuestionOut | TrueFalseQuestionOut | ClozeQuestionOut | FreeQuestionOut,
    Field(discriminator="kind"),
]
QUESTION: TypeAdapter[QuestionOut] = TypeAdapter(QuestionOut)


class McViewOut(McQuestionOut):
    source: str


class TrueFalseViewOut(TrueFalseQuestionOut):
    source: str


class ClozeViewOut(ClozeQuestionOut):
    source: str


class FreeViewOut(FreeQuestionOut):
    source: str


ItemViewOut = Annotated[
    McViewOut | TrueFalseViewOut | ClozeViewOut | FreeViewOut, Field(discriminator="kind")
]
_ITEM_VIEW: TypeAdapter[ItemViewOut] = TypeAdapter(ItemViewOut)


class ChapterViewOut(BaseModel):
    id: int
    title: str
    summary: str | None
    concepts: list[Concept]
    source: str


class IntroEntryOut(BaseModel):
    n: int
    type: Literal["intro"]
    done: bool
    grading_unavailable: bool
    chapter: ChapterViewOut


class ItemEntryOut(BaseModel):
    n: int
    type: Literal["item"]
    done: bool
    grading_unavailable: bool
    model_answer: str | None
    item: ItemViewOut


EntryOut = Annotated[IntroEntryOut | ItemEntryOut, Field(discriminator="type")]


class RunOut(BaseModel):
    id: int | None
    subject_id: int | None
    subject_name: str | None
    entries: list[EntryOut]


class CurrentRunOut(BaseModel):
    run: RunOut | None


class OpenRunOut(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    created_at: datetime
    open_items: int


class DoneOut(BaseModel):
    done: Literal[True]


class ObjectiveResultOut(BaseModel):
    correct: bool
    expected: str
    explanation: str


class FreeResultOut(BaseModel):
    score: int
    feedback: str
    missing: list[str]
    model_answer: str


class GradingUnavailableOut(BaseModel):
    grading_unavailable: Literal[True]
    reason: str
    model_answer: str


class RunSummaryOut(BaseModel):
    answered: int
    correct: int
    chapters_introduced: list[str]
    due_tomorrow: int


def pdf_link(booklet_id: int, page: int) -> str:
    return f"/api/booklets/{booklet_id}/pdf#page={page}"


async def _get_run(session: AsyncSession, run_id: int) -> Run:
    run = (
        await session.scalars(select(Run).where(Run.id == run_id).with_for_update())
    ).one_or_none()
    if run is None:
        raise HTTPException(404, "Durchlauf nicht gefunden")
    return run


def _entry(run: Run, n: int) -> dict[str, Any]:
    if not 0 <= n < len(run.entries):
        raise HTTPException(404, "Eintrag nicht gefunden")
    return run.entries[n]


def _store(run: Run, n: int, entry: dict[str, Any]) -> None:
    run.entries = [entry if i == n else e for i, e in enumerate(run.entries)]


async def _subject(session: AsyncSession, subject_id: int | None) -> Subject | None:
    if subject_id is None:
        return None
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Fach nicht gefunden")
    return subject


async def _run_out(session: AsyncSession, run: Run) -> RunOut:
    chapter_ids = [e["chapter_id"] for e in run.entries if e["type"] == "intro"]
    item_ids = [e["item_id"] for e in run.entries if e["type"] == "item"]
    chapters = {
        chapter.id: (chapter, booklet_id)
        for chapter, booklet_id in (
            await session.execute(
                select(Chapter, Chapter.booklet_id).where(Chapter.id.in_(chapter_ids))
            )
        ).all()
    }
    items = {
        item.id: (item, booklet_id)
        for item, booklet_id in (
            await session.execute(
                select(Item, Chapter.booklet_id)
                .join(Chapter, Chapter.id == Item.chapter_id)
                .where(Item.id.in_(item_ids))
            )
        ).all()
    }
    entries: list[IntroEntryOut | ItemEntryOut] = []
    for n, entry in enumerate(run.entries):
        done = bool(entry.get("done"))
        unavailable = bool(entry.get("grading_unavailable"))
        if entry["type"] == "intro":
            chapter, booklet_id = chapters[entry["chapter_id"]]
            entries.append(
                IntroEntryOut(
                    n=n,
                    type="intro",
                    done=done,
                    grading_unavailable=unavailable,
                    chapter=ChapterViewOut(
                        id=chapter.id,
                        title=chapter.title,
                        summary=chapter.summary,
                        concepts=[Concept.model_validate(c) for c in chapter.concepts],
                        source=pdf_link(booklet_id, chapter.first_page),
                    ),
                )
            )
        else:
            item, booklet_id = items[entry["item_id"]]
            view = public_view(item) | {"source": pdf_link(booklet_id, item.source_page)}
            entries.append(
                ItemEntryOut(
                    n=n,
                    type="item",
                    done=done,
                    grading_unavailable=unavailable,
                    model_answer=item.payload.get("model_answer") if unavailable else None,
                    item=_ITEM_VIEW.validate_python(view),
                )
            )
    subject = await _subject(session, run.subject_id)
    return RunOut(
        id=run.id,
        subject_id=run.subject_id,
        subject_name=None if subject is None else subject.name,
        entries=entries,
    )


async def _unfinished_run(
    session: AsyncSession, settings: Settings, now: datetime, subject_id: int | None
) -> Run | None:
    local_date = now.astimezone(ZoneInfo(settings.timezone)).date()
    kind = (
        and_(Run.subject_id.is_(None), Run.local_date == local_date)
        if subject_id is None
        else Run.subject_id == subject_id
    )
    return (
        await session.scalars(
            select(Run).where(kind, Run.finished_at.is_(None)).order_by(Run.id.desc()).limit(1)
        )
    ).first()


@router.get("/runs/current")
async def current_run(
    session: Session, settings: AppSettings, now: Now, subject_id: int | None = None
) -> CurrentRunOut:
    await _subject(session, subject_id)
    run = await _unfinished_run(session, settings, now, subject_id)
    return CurrentRunOut(run=None if run is None else await _run_out(session, run))


@router.get("/runs/open")
async def open_runs(session: Session) -> list[OpenRunOut]:
    rows = await session.execute(
        select(Run, Subject.id, Subject.name)
        .join(Subject, Subject.id == Run.subject_id)
        .where(Run.finished_at.is_(None))
        .order_by(Run.created_at, Run.id)
    )
    return [
        OpenRunOut(
            id=run.id,
            subject_id=subject_id,
            subject_name=name,
            created_at=run.created_at,
            open_items=sum(1 for e in run.entries if e["type"] == "item" and not e.get("done")),
        )
        for run, subject_id, name in rows.all()
    ]


@router.post("/runs")
async def start_run(
    session: Session, settings: AppSettings, now: Now, body: StartRunIn | None = None
) -> RunOut:
    subject_id = None if body is None else body.subject_id
    subject = await _subject(session, subject_id)
    run = await _unfinished_run(session, settings, now, subject_id)
    if run is None:
        entries = await build_run(session, settings, now, subject_id=subject_id)
        if not entries:
            return RunOut(
                id=None,
                subject_id=subject_id,
                subject_name=None if subject is None else subject.name,
                entries=[],
            )
        local_date = now.astimezone(ZoneInfo(settings.timezone)).date()
        run = Run(local_date=local_date, subject_id=subject_id, entries=entries, created_at=now)
        session.add(run)
        await session.flush()
    return await _run_out(session, run)


@router.post("/runs/{run_id}/entries/{n}/ack")
async def ack_intro(run_id: int, n: int, session: Session, now: Now) -> DoneOut:
    run = await _get_run(session, run_id)
    entry = _entry(run, n)
    if entry["type"] != "intro":
        raise HTTPException(409, "Dieser Eintrag ist keine Einführung.")
    chapter = await session.get(Chapter, entry["chapter_id"])
    if chapter is not None and chapter.introduced_at is None:
        chapter.introduced_at = now
    _store(run, n, {**entry, "done": True})
    await session.flush()
    return DoneOut(done=True)


def _item_entry(run: Run, n: int) -> dict[str, Any]:
    entry = _entry(run, n)
    if entry["type"] != "item":
        raise HTTPException(409, "Dieser Eintrag ist keine Frage.")
    if entry.get("done"):
        raise HTTPException(409, "Diese Frage ist schon beantwortet.")
    return entry


async def _item(session: AsyncSession, entry: dict[str, Any]) -> Item:
    item = await session.get(Item, entry["item_id"])
    if item is None:
        raise HTTPException(404, "Frage nicht gefunden")
    return item


@router.post("/runs/{run_id}/entries/{n}/answer")
async def answer(
    run_id: int, n: int, body: AnswerIn, session: Session, now: Now, llm: Llm
) -> ObjectiveResultOut | FreeResultOut | GradingUnavailableOut:
    run = await _get_run(session, run_id)
    entry = _item_entry(run, n)
    item = await _item(session, entry)

    if item.kind != ItemKind.free:
        try:
            result = check_objective(item, body.answer)
        except ValueError as exc:
            raise HTTPException(422, "Ungültige Antwort.") from exc
        await record_review(
            session,
            item.id,
            rating_for_objective(result.correct),
            now,
            correct=result.correct,
            score=None,
        )
        _store(run, n, {**entry, "done": True, "correct": result.correct})
        await session.flush()
        return ObjectiveResultOut(
            correct=result.correct, expected=result.expected, explanation=result.explanation
        )

    if entry.get("grading_unavailable"):
        raise HTTPException(409, "Bitte bewerte diese Antwort selbst.")
    text = body.answer.get("text")
    if not isinstance(text, str):
        raise HTTPException(422, "Ungültige Antwort.")
    model_answer = item.payload["model_answer"]
    reason: str | None = None
    try:
        grade = await grade_free(session, llm, item, text, now)
    except BudgetExceeded:
        reason = "Tagesbudget erreicht"
    except LLMUnavailable:
        reason = "Bewertung gerade nicht möglich"
    if reason is not None:
        _store(run, n, {**entry, "grading_unavailable": True})
        await session.flush()
        return GradingUnavailableOut(
            grading_unavailable=True, reason=reason, model_answer=model_answer
        )

    await record_review(
        session, item.id, rating_for_score(grade.score), now, correct=None, score=grade.score
    )
    _store(
        run,
        n,
        {**entry, "done": True, "correct": grade.score >= 75, "grading_unavailable": False},
    )
    await session.flush()
    return FreeResultOut(
        score=grade.score,
        feedback=grade.feedback,
        missing=grade.missing,
        model_answer=model_answer,
    )


@router.post("/runs/{run_id}/entries/{n}/self-rate")
async def self_rate(run_id: int, n: int, body: SelfRateIn, session: Session, now: Now) -> DoneOut:
    run = await _get_run(session, run_id)
    entry = _item_entry(run, n)
    if not entry.get("grading_unavailable"):
        raise HTTPException(409, "Selbstbewertung ist nur möglich, wenn die Bewertung ausfällt.")
    good = body.rating == "good"
    await record_review(
        session,
        entry["item_id"],
        Rating.Good if good else Rating.Again,
        now,
        correct=good,
        score=None,
    )
    _store(run, n, {**entry, "done": True, "correct": good})
    await session.flush()
    return DoneOut(done=True)


@router.post("/runs/{run_id}/finish")
async def finish(run_id: int, session: Session, settings: AppSettings, now: Now) -> RunSummaryOut:
    run = await _get_run(session, run_id)
    if run.finished_at is None:
        run.finished_at = now
    items = [e for e in run.entries if e["type"] == "item" and e.get("done")]
    chapter_ids = [e["chapter_id"] for e in run.entries if e["type"] == "intro" and e.get("done")]
    titles = {
        c.id: c.title
        for c in (await session.scalars(select(Chapter).where(Chapter.id.in_(chapter_ids))))
    }
    _, today_end = local_day_bounds(now, settings.timezone)
    tomorrow_end = local_day_bounds(today_end + timedelta(hours=12), settings.timezone)[1]
    due_count = await session.scalar(
        select(func.count())
        .select_from(ReviewState)
        .join(Item, Item.id == ReviewState.item_id)
        .join(Chapter, Chapter.id == Item.chapter_id)
        .where(
            Item.status == ItemStatus.active,
            Chapter.status == ChapterStatus.ready,
            ReviewState.due < tomorrow_end,
        )
    )
    await session.flush()
    return RunSummaryOut(
        answered=len(items),
        correct=sum(1 for e in items if e.get("correct")),
        chapters_introduced=[titles[i] for i in chapter_ids if i in titles],
        due_tomorrow=min(due_count or 0, settings.run_review_cap),
    )
