from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.config import Settings
from studyrun.models.db import ExamAttempt, Semester, Subject
from studyrun.planning.effort import subject_effort
from studyrun.planning.pace import measured_pace
from studyrun.planning.planner import Plan, PlanSubject, plan


async def plan_inputs(session: AsyncSession) -> tuple[list[PlanSubject], dict[str, date]]:
    semesters = {s.label: s.starts_on for s in await session.scalars(select(Semester))}
    attempts: dict[int, list[ExamAttempt]] = {}
    for attempt in await session.scalars(select(ExamAttempt).order_by(ExamAttempt.id)):
        attempts.setdefault(attempt.subject_id, []).append(attempt)
    subjects: list[PlanSubject] = []
    for subject in await session.scalars(select(Subject).order_by(Subject.id)):
        effort, has_material = await subject_effort(session, subject.id)
        subjects.append(
            PlanSubject(
                id=subject.id,
                name=subject.name,
                earliest_semester=subject.earliest_semester,
                recommended_semester=subject.recommended_semester,
                not_before=subject.not_before,
                sittings=[date.fromisoformat(d) for d in subject.sittings],
                effort_items=effort,
                has_material=has_material,
                attempts=[(a.sitting, a.status) for a in attempts.get(subject.id, [])],
            )
        )
    return subjects, semesters


def local_today(settings: Settings, now: datetime) -> date:
    return now.astimezone(ZoneInfo(settings.timezone)).date()


async def current_plan(session: AsyncSession, settings: Settings, now: datetime) -> Plan:
    subjects, semesters = await plan_inputs(session)
    pace = await measured_pace(session, settings, now)
    return plan(subjects, semesters, local_today(settings, now), pace)
