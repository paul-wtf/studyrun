from __future__ import annotations

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.models.db import AttemptStatus, ExamAttempt, Module, Semester, Subject
from studyrun.routes.modules import Session
from studyrun.routes.runs import AppSettings, Now

router = APIRouter()

OPEN = (AttemptStatus.planned, AttemptStatus.registered)


class AttemptOut(BaseModel):
    id: int
    sitting: date
    status: AttemptStatus


class SubjectOut(BaseModel):
    id: int
    name: str
    duration_minutes: int
    earliest_semester: str
    recommended_semester: int | None
    not_before: date | None
    pass_mark: int
    sittings: list[str]
    module_ids: list[int]
    attempts: list[AttemptOut]


class SemesterOut(BaseModel):
    label: str
    starts_on: date


class SemesterPut(BaseModel):
    starts_on: date


class SubjectImportEntry(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    duration_minutes: int = Field(gt=0)
    earliest_semester: str = Field(min_length=1, max_length=16)
    recommended_semester: int | None = Field(default=None, gt=0)
    sittings: list[date]


class SubjectImport(BaseModel):
    semesters: dict[str, date]
    subjects: list[SubjectImportEntry]

    @model_validator(mode="after")
    def _unique_names(self) -> SubjectImport:
        names = [s.name for s in self.subjects]
        if len(set(names)) != len(names):
            raise ValueError("Fachnamen müssen eindeutig sein")
        return self


class ImportOut(BaseModel):
    created: int
    updated: int


class SubjectPatch(BaseModel):
    not_before: date | None = None
    pass_mark: int | None = Field(default=None, ge=1, le=100)


class AttemptCreate(BaseModel):
    sitting: date
    status: Literal["planned", "registered"]


class AttemptPatch(BaseModel):
    status: AttemptStatus


def _normalize(sittings: list[date]) -> list[str]:
    return sorted({d.isoformat() for d in sittings})


async def _subjects_out(session: AsyncSession, subjects: list[Subject]) -> list[SubjectOut]:
    ids = [s.id for s in subjects]
    modules: dict[int, list[int]] = {i: [] for i in ids}
    for subject_id, module_id in await session.execute(
        select(Module.subject_id, Module.id)
        .where(Module.subject_id.in_(ids))
        .order_by(Module.position, Module.id)
    ):
        if subject_id is not None:
            modules[subject_id].append(module_id)
    attempts: dict[int, list[AttemptOut]] = {i: [] for i in ids}
    for attempt in await session.scalars(
        select(ExamAttempt)
        .where(ExamAttempt.subject_id.in_(ids))
        .order_by(ExamAttempt.sitting, ExamAttempt.id)
    ):
        attempts[attempt.subject_id].append(
            AttemptOut(id=attempt.id, sitting=attempt.sitting, status=attempt.status)
        )
    return [
        SubjectOut(
            id=s.id,
            name=s.name,
            duration_minutes=s.duration_minutes,
            earliest_semester=s.earliest_semester,
            recommended_semester=s.recommended_semester,
            not_before=s.not_before,
            pass_mark=s.pass_mark,
            sittings=list(s.sittings),
            module_ids=modules[s.id],
            attempts=attempts[s.id],
        )
        for s in subjects
    ]


async def _get_subject(session: AsyncSession, subject_id: int) -> Subject:
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Fach nicht gefunden")
    return subject


async def _get_attempt(session: AsyncSession, attempt_id: int) -> ExamAttempt:
    attempt = await session.get(ExamAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(404, "Prüfungsversuch nicht gefunden")
    return attempt


def _local_today(settings: AppSettings, now: Now) -> date:
    return now.astimezone(ZoneInfo(settings.timezone)).date()


@router.post("/subjects/import")
async def import_subjects(body: SubjectImport, session: Session) -> ImportOut:
    for label, starts_on in body.semesters.items():
        semester = await session.get(Semester, label)
        if semester is None:
            session.add(Semester(label=label, starts_on=starts_on))
        else:
            semester.starts_on = starts_on
    existing = {
        s.name: s
        for s in await session.scalars(
            select(Subject).where(Subject.name.in_([e.name for e in body.subjects]))
        )
    }
    created = updated = 0
    for entry in body.subjects:
        subject = existing.get(entry.name)
        if subject is None:
            subject = Subject(name=entry.name)
            session.add(subject)
            created += 1
        else:
            updated += 1
        subject.duration_minutes = entry.duration_minutes
        subject.earliest_semester = entry.earliest_semester
        subject.recommended_semester = entry.recommended_semester
        subject.sittings = _normalize(entry.sittings)
    await session.flush()
    return ImportOut(created=created, updated=updated)


@router.get("/subjects")
async def list_subjects(session: Session) -> list[SubjectOut]:
    subjects = list(await session.scalars(select(Subject).order_by(Subject.id)))
    return await _subjects_out(session, subjects)


@router.get("/subjects/{subject_id}")
async def get_subject(subject_id: int, session: Session) -> SubjectOut:
    subject = await _get_subject(session, subject_id)
    return (await _subjects_out(session, [subject]))[0]


@router.patch("/subjects/{subject_id}")
async def patch_subject(subject_id: int, body: SubjectPatch, session: Session) -> SubjectOut:
    subject = await _get_subject(session, subject_id)
    if "not_before" in body.model_fields_set:
        subject.not_before = body.not_before
    if body.pass_mark is not None:
        subject.pass_mark = body.pass_mark
    await session.flush()
    return (await _subjects_out(session, [subject]))[0]


@router.get("/semesters")
async def list_semesters(session: Session) -> list[SemesterOut]:
    rows = await session.scalars(select(Semester).order_by(Semester.label))
    return [SemesterOut(label=r.label, starts_on=r.starts_on) for r in rows]


@router.put("/semesters/{label}")
async def put_semester(label: str, body: SemesterPut, session: Session) -> SemesterOut:
    semester = await session.get(Semester, label)
    if semester is None:
        semester = Semester(label=label, starts_on=body.starts_on)
        session.add(semester)
    else:
        semester.starts_on = body.starts_on
    await session.flush()
    return SemesterOut(label=label, starts_on=body.starts_on)


@router.post("/subjects/{subject_id}/attempts", status_code=201)
async def create_attempt(
    subject_id: int, body: AttemptCreate, session: Session, settings: AppSettings, now: Now
) -> AttemptOut:
    subject = await _get_subject(session, subject_id)
    if body.sitting.isoformat() not in subject.sittings:
        raise HTTPException(422, "Der Termin gehört nicht zu den Prüfungsterminen dieses Fachs")
    today = _local_today(settings, now)
    await session.execute(
        delete(ExamAttempt).where(
            ExamAttempt.subject_id == subject_id,
            ExamAttempt.status.in_(OPEN),
            ExamAttempt.sitting >= today,
        )
    )
    attempt = ExamAttempt(
        subject_id=subject_id, sitting=body.sitting, status=AttemptStatus(body.status)
    )
    session.add(attempt)
    await session.flush()
    return AttemptOut(id=attempt.id, sitting=attempt.sitting, status=attempt.status)


@router.patch("/attempts/{attempt_id}")
async def patch_attempt(
    attempt_id: int, body: AttemptPatch, session: Session, settings: AppSettings, now: Now
) -> AttemptOut:
    attempt = await _get_attempt(session, attempt_id)
    if body.status in (AttemptStatus.passed, AttemptStatus.failed) and attempt.sitting > (
        _local_today(settings, now)
    ):
        raise HTTPException(409, "Ein Ergebnis gibt es erst ab dem Prüfungstag")
    attempt.status = body.status
    await session.flush()
    return AttemptOut(id=attempt.id, sitting=attempt.sitting, status=attempt.status)


@router.delete("/attempts/{attempt_id}", status_code=204)
async def delete_attempt(attempt_id: int, session: Session) -> Response:
    attempt = await _get_attempt(session, attempt_id)
    if attempt.status not in OPEN:
        raise HTTPException(409, "Nur geplante oder angemeldete Versuche lassen sich löschen")
    await session.delete(attempt)
    await session.flush()
    return Response(status_code=204)
