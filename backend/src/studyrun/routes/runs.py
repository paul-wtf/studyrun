from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fsrs import Rating
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.clock import local_day_bounds
from studyrun.ai.llm import LLM, LLMUnavailable
from studyrun.config import Settings
from studyrun.content.schemas import Concept
from studyrun.deps import get_llm, get_now, get_settings
from studyrun.models.db import Chapter, ChapterStatus, Item, ItemKind, ItemStatus, ReviewState, Run
from studyrun.routes.modules import Session
from studyrun.study.answers import check_objective, public_view
from studyrun.study.assemble import build_run
from studyrun.study.grading import grade_free
from studyrun.study.scheduling import rating_for_objective, rating_for_score, record_review

router = APIRouter()

Now = Annotated[datetime, Depends(get_now)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Llm = Annotated[LLM, Depends(get_llm)]


class AnswerIn(BaseModel):
    answer: dict[str, Any]


class SelfRateIn(BaseModel):
    rating: Literal["again", "good"]


class McViewOut(BaseModel):
    id: int
    kind: Literal["mc"]
    prompt: str
    options: list[str]
    source: str


class TrueFalseViewOut(BaseModel):
    id: int
    kind: Literal["true_false"]
    statement: str
    source: str


class ClozeViewOut(BaseModel):
    id: int
    kind: Literal["cloze"]
    text: str
    source: str


class FreeViewOut(BaseModel):
    id: int
    kind: Literal["free"]
    prompt: str
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
    item: ItemViewOut


EntryOut = Annotated[IntroEntryOut | ItemEntryOut, Field(discriminator="type")]


class RunOut(BaseModel):
    id: int | None
    entries: list[EntryOut]


class CurrentRunOut(BaseModel):
    run: RunOut | None


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
                    item=_ITEM_VIEW.validate_python(view),
                )
            )
    return RunOut(id=run.id, entries=entries)


async def _unfinished_run(session: AsyncSession, settings: Settings, now: datetime) -> Run | None:
    local_date = now.astimezone(ZoneInfo(settings.timezone)).date()
    return (
        await session.scalars(
            select(Run)
            .where(Run.local_date == local_date, Run.finished_at.is_(None))
            .order_by(Run.id.desc())
            .limit(1)
        )
    ).first()


@router.get("/runs/current")
async def current_run(session: Session, settings: AppSettings, now: Now) -> CurrentRunOut:
    run = await _unfinished_run(session, settings, now)
    return CurrentRunOut(run=None if run is None else await _run_out(session, run))


@router.post("/runs")
async def start_run(session: Session, settings: AppSettings, now: Now) -> RunOut:
    run = await _unfinished_run(session, settings, now)
    if run is None:
        entries = await build_run(session, settings, now)
        if not entries:
            return RunOut(id=None, entries=[])
        local_date = now.astimezone(ZoneInfo(settings.timezone)).date()
        run = Run(local_date=local_date, entries=entries)
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
        raise HTTPException(409, "Dieser Eintrag ist keine Aufgabe.")
    if entry.get("done"):
        raise HTTPException(409, "Diese Aufgabe ist schon beantwortet.")
    return entry


async def _item(session: AsyncSession, entry: dict[str, Any]) -> Item:
    item = await session.get(Item, entry["item_id"])
    if item is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
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
