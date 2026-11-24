from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from studyrun.deps import get_now
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Module, Subject

IMPORT = {
    "semesters": {"3a": "2026-04-01", "4a": "2026-10-01", "5a": "2027-04-01"},
    "subjects": [
        {
            "name": "Alpha",
            "duration_minutes": 90,
            "earliest_semester": "3a",
            "recommended_semester": 4,
            "sittings": ["2027-02-14", "2027-05-16"],
        },
        {
            "name": "Beta",
            "duration_minutes": 90,
            "earliest_semester": "3a",
            "recommended_semester": 4,
            "sittings": ["2027-02-14", "2027-05-16"],
        },
        {
            "name": "Gamma",
            "duration_minutes": 180,
            "earliest_semester": "5a",
            "sittings": ["2027-05-16"],
        },
        {"name": "Delta", "duration_minutes": 90, "earliest_semester": "6a", "sittings": []},
    ],
}


async def _give_material(session, name, pages):
    subject = await session.scalar(select(Subject).where(Subject.name == name))
    module = Module(name=f"Modul {name}", position=0, subject_id=subject.id)
    session.add(module)
    await session.flush()
    booklet = Booklet(module_id=module.id, filename="b.pdf", pdf=b"", page_count=pages)
    session.add(booklet)
    await session.flush()
    session.add(
        Chapter(
            booklet_id=booklet.id,
            index=0,
            title="Kapitel",
            first_page=1,
            last_page=pages,
            status=ChapterStatus.pending,
        )
    )
    await session.flush()
    return subject.id


async def test_plan_proposes_registers_and_reports_conflicts(api, db_session):
    client, app = api
    app.dependency_overrides[get_now] = lambda: datetime(2026, 11, 24, 12, tzinfo=UTC)
    assert (await client.post("/api/subjects/import", json=IMPORT)).status_code == 200
    alpha = await _give_material(db_session, "Alpha", 10)
    beta = await _give_material(db_session, "Beta", 10)

    body = (await client.get("/api/plan")).json()
    entries = {e["subject_name"]: e for e in body["entries"]}
    assert body["pace_per_day"] == pytest.approx(4 * 4 / 7)
    assert entries["Alpha"] == {
        "subject_id": alpha,
        "subject_name": "Alpha",
        "state": "open",
        "sitting": "2027-02-14",
        "register_by": "2027-01-24",
        "feasible": True,
        "study_from": "2026-11-24",
        "study_until": "2026-12-03",
    }
    assert (entries["Beta"]["sitting"], entries["Beta"]["study_from"]) == (
        "2027-05-16",
        "2026-12-03",
    )
    assert entries["Gamma"]["state"] == "no_material"
    assert entries["Delta"]["state"] == "not_plannable"
    assert body["order"] == [alpha, beta]
    assert sorted((c["subject_name"], c["kind"]) for c in body["conflicts"]) == [
        ("Delta", "missing_semester"),
        ("Gamma", "no_material"),
    ]

    resp = await client.post(
        f"/api/subjects/{beta}/attempts", json={"sitting": "2027-02-14", "status": "registered"}
    )
    assert resp.status_code == 201
    body = (await client.get("/api/plan")).json()
    entries = {e["subject_name"]: e for e in body["entries"]}
    assert (entries["Beta"]["state"], entries["Beta"]["register_by"]) == ("registered", None)
    assert entries["Alpha"]["sitting"] == "2027-05-16"
    assert body["order"] == [beta, alpha]
