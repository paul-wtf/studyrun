from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from studyrun.models.db import (
    AttemptStatus,
    ExamAttempt,
    MockExam,
    Module,
    Run,
    Semester,
    Subject,
)


def _subject(name="Statistik") -> Subject:
    return Subject(
        name=name,
        duration_minutes=90,
        earliest_semester="3a",
        sittings=["2027-02-10", "2027-07-14"],
    )


async def test_subject_defaults(db_session):
    subject = _subject()
    db_session.add(subject)
    await db_session.flush()
    await db_session.refresh(subject)
    assert subject.pass_mark == 50
    assert subject.recommended_semester is None
    assert subject.not_before is None
    assert subject.created_at is not None


async def test_semester_roundtrip(db_session):
    db_session.add(Semester(label="3a", starts_on=date(2027, 4, 1)))
    await db_session.flush()
    semester = await db_session.get(Semester, "3a")
    assert semester is not None
    assert semester.starts_on == date(2027, 4, 1)


async def test_subject_cascade_deletes_attempts_and_mock_exams(db_session):
    subject = _subject()
    db_session.add(subject)
    await db_session.flush()
    db_session.add(
        ExamAttempt(subject_id=subject.id, sitting=date(2027, 2, 10), status=AttemptStatus.planned)
    )
    db_session.add(
        MockExam(
            subject_id=subject.id,
            deadline=datetime(2027, 1, 1, 12, tzinfo=UTC),
            entries=[],
            pass_mark=50,
        )
    )
    await db_session.flush()

    await db_session.execute(delete(Subject).where(Subject.id == subject.id))

    assert await db_session.scalar(select(func.count()).select_from(ExamAttempt)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MockExam)) == 0


async def test_module_subject_set_null_on_delete(db_session):
    subject = _subject()
    db_session.add(subject)
    await db_session.flush()
    module = Module(name="Statistik", position=0, subject_id=subject.id)
    run = Run(local_date=date(2027, 1, 1), entries=[], subject_id=subject.id)
    db_session.add_all([module, run])
    await db_session.flush()

    await db_session.execute(delete(Subject).where(Subject.id == subject.id))
    await db_session.refresh(module)
    await db_session.refresh(run)

    assert module.subject_id is None
    assert run.subject_id is None


async def test_subject_name_unique(db_session):
    db_session.add(_subject())
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                insert(Subject).values(
                    name="Statistik", duration_minutes=60, earliest_semester="3a"
                )
            )
