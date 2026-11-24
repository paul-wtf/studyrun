from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from studyrun.planning import current_plan
from studyrun.planning.planner import ConflictKind, EntryState
from studyrun.routes.modules import Session
from studyrun.routes.runs import AppSettings, Now

router = APIRouter()


class PlanEntryOut(BaseModel):
    subject_id: int
    subject_name: str
    state: EntryState
    sitting: date | None
    register_by: date | None
    feasible: bool
    study_from: date | None
    study_until: date | None


class ConflictOut(BaseModel):
    subject_id: int
    subject_name: str
    kind: ConflictKind
    message: str


class PlanOut(BaseModel):
    entries: list[PlanEntryOut]
    conflicts: list[ConflictOut]
    order: list[int]
    pace_per_day: float


@router.get("/plan")
async def get_plan(session: Session, settings: AppSettings, now: Now) -> PlanOut:
    current = await current_plan(session, settings, now)
    result = current.plan
    names = {s.id: s.name for s in current.subjects}
    return PlanOut(
        entries=[
            PlanEntryOut(
                subject_id=e.subject_id,
                subject_name=names[e.subject_id],
                state=e.state,
                sitting=e.sitting,
                register_by=e.register_by,
                feasible=e.feasible,
                study_from=e.study_from,
                study_until=e.study_until,
            )
            for e in result.entries
        ],
        conflicts=[
            ConflictOut(
                subject_id=c.subject_id,
                subject_name=names[c.subject_id],
                kind=c.kind,
                message=c.message_de,
            )
            for c in result.conflicts
        ],
        order=result.order,
        pace_per_day=current.pace_per_day,
    )
