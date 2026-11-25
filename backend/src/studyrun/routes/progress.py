from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from studyrun.ai.clock import local_day_bounds
from studyrun.models.db import (
    Booklet,
    Chapter,
    ChapterStatus,
    Item,
    ItemStatus,
    Module,
    ReviewLog,
    ReviewState,
    Subject,
)
from studyrun.routes.modules import Session
from studyrun.routes.runs import AppSettings, Now
from studyrun.study.scheduling import retrievability

router = APIRouter()

SOLID_RECALL = 0.9


class WeekDayOut(BaseModel):
    date: date
    done: bool


class WeekOut(BaseModel):
    days: list[WeekDayOut]
    goal: int
    done_count: int


class SubjectProgressOut(BaseModel):
    subject_id: int
    introduced: float
    solid: float


class ProgressOut(BaseModel):
    week: WeekOut
    subjects: list[SubjectProgressOut]


def _noon(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(12), tzinfo=zone)


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


@router.get("/progress")
async def get_progress(session: Session, settings: AppSettings, now: Now) -> ProgressOut:
    zone = ZoneInfo(settings.timezone)
    today = now.astimezone(zone).date()
    monday = today - timedelta(days=today.weekday())
    days = [monday + timedelta(days=n) for n in range(7)]
    start = local_day_bounds(_noon(monday, zone), settings.timezone)[0]
    end = local_day_bounds(_noon(days[-1], zone), settings.timezone)[1]
    answered = await session.scalars(
        select(ReviewLog.answered_at).where(
            ReviewLog.answered_at >= start, ReviewLog.answered_at < end
        )
    )
    active_days = {at.astimezone(zone).date() for at in answered}
    week_days = [WeekDayOut(date=d, done=d in active_days) for d in days]

    subject_ids = list(await session.scalars(select(Subject.id).order_by(Subject.id)))
    chapters = await session.execute(
        select(Module.subject_id, Chapter.status, Chapter.introduced_at)
        .join(Booklet, Booklet.module_id == Module.id)
        .join(Chapter, Chapter.booklet_id == Booklet.id)
        .where(Module.subject_id.is_not(None))
    )
    introduced: dict[int, list[int]] = {sid: [0, 0] for sid in subject_ids}
    for subject_id, status, introduced_at in chapters:
        if subject_id is None or status == ChapterStatus.skipped:
            continue
        introduced[subject_id][1] += 1
        introduced[subject_id][0] += introduced_at is not None

    items = await session.execute(
        select(Module.subject_id, ReviewState.card)
        .select_from(Item)
        .join(Chapter, Chapter.id == Item.chapter_id)
        .join(Booklet, Booklet.id == Chapter.booklet_id)
        .join(Module, Module.id == Booklet.module_id)
        .outerjoin(ReviewState, ReviewState.item_id == Item.id)
        .where(
            Module.subject_id.is_not(None),
            Item.status == ItemStatus.active,
            Chapter.status == ChapterStatus.ready,
        )
    )
    solid: dict[int, list[int]] = {sid: [0, 0] for sid in subject_ids}
    for subject_id, card in items:
        if subject_id is None:
            continue
        solid[subject_id][1] += 1
        solid[subject_id][0] += retrievability(card, now) >= SOLID_RECALL

    return ProgressOut(
        week=WeekOut(
            days=week_days,
            goal=settings.weekly_goal_days,
            done_count=sum(d.done for d in week_days),
        ),
        subjects=[
            SubjectProgressOut(
                subject_id=sid,
                introduced=_share(*introduced[sid]),
                solid=_share(*solid[sid]),
            )
            for sid in subject_ids
        ],
    )
