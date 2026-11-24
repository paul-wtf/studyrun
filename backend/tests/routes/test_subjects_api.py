from datetime import UTC, datetime

from studyrun.deps import get_now

IMPORT = {
    "semesters": {"3a": "2026-10-01", "3b": "2027-01-04"},
    "subjects": [
        {
            "name": "Alpha",
            "duration_minutes": 90,
            "earliest_semester": "3a",
            "recommended_semester": 3,
            "sittings": ["2027-03-10", "2027-02-01", "2027-02-01"],
        },
        {"name": "Beta", "duration_minutes": 60, "earliest_semester": "3b", "sittings": []},
    ],
}


def _today(app, y, m, d):
    app.dependency_overrides[get_now] = lambda: datetime(y, m, d, 12, tzinfo=UTC)


async def _import(client, body=None):
    resp = await client.post("/api/subjects/import", json=body or IMPORT)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _subject(client, name):
    return next(s for s in (await client.get("/api/subjects")).json() if s["name"] == name)


async def test_import_creates_then_updates_keeping_state(api):
    client, app = api
    _today(app, 2026, 11, 1)
    assert await _import(client) == {"created": 2, "updated": 0}
    alpha = await _subject(client, "Alpha")
    assert alpha["sittings"] == ["2027-02-01", "2027-03-10"]
    assert alpha["pass_mark"] == 50
    assert alpha["attempts"] == []

    assert (
        await client.patch(
            f"/api/subjects/{alpha['id']}", json={"not_before": "2027-01-01", "pass_mark": 60}
        )
    ).status_code == 200
    module = (await client.post("/api/modules", json={"name": "M"})).json()
    resp = await client.patch(f"/api/modules/{module['id']}", json={"subject_id": alpha["id"]})
    assert resp.json()["subject_id"] == alpha["id"]
    await client.post(
        f"/api/subjects/{alpha['id']}/attempts", json={"sitting": "2027-02-01", "status": "planned"}
    )

    changed = {
        "semesters": {"3a": "2026-10-05"},
        "subjects": [
            {
                "name": "Alpha",
                "duration_minutes": 120,
                "earliest_semester": "3b",
                "sittings": ["2027-02-01"],
            }
        ],
    }
    assert await _import(client, changed) == {"created": 0, "updated": 1}
    alpha = await _subject(client, "Alpha")
    assert alpha["duration_minutes"] == 120
    assert alpha["earliest_semester"] == "3b"
    assert alpha["not_before"] == "2027-01-01"
    assert alpha["pass_mark"] == 60
    assert alpha["module_ids"] == [module["id"]]
    assert len(alpha["attempts"]) == 1
    semesters = {s["label"]: s["starts_on"] for s in (await client.get("/api/semesters")).json()}
    assert semesters == {"3a": "2026-10-05", "3b": "2027-01-04"}


async def test_import_rejects_bad_shapes(api):
    client, _ = api
    sub = IMPORT["subjects"][0]
    bad = [
        {"semesters": {"3a": "kein-datum"}, "subjects": []},
        {"semesters": {}, "subjects": [{**sub, "sittings": ["2027-13-40"]}]},
        {"semesters": {}, "subjects": [{**sub, "duration_minutes": 0}]},
        {"semesters": {}, "subjects": [{**sub, "name": ""}]},
        {"semesters": {}, "subjects": [sub, sub]},
        {"subjects": []},
    ]
    for body in bad:
        assert (await client.post("/api/subjects/import", json=body)).status_code == 422, body
    assert (await client.get("/api/subjects")).json() == []


async def test_semester_put_and_subject_patch_validation(api):
    client, _ = api
    resp = await client.put("/api/semesters/4a", json={"starts_on": "2027-04-01"})
    assert resp.json() == {"label": "4a", "starts_on": "2027-04-01"}
    assert (await client.put("/api/semesters/4a", json={"starts_on": "x"})).status_code == 422
    await _import(client)
    alpha = await _subject(client, "Alpha")
    for mark in (0, 101):
        resp = await client.patch(f"/api/subjects/{alpha['id']}", json={"pass_mark": mark})
        assert resp.status_code == 422
    assert (await client.get("/api/subjects/999")).status_code == 404
    assert (await client.patch("/api/subjects/999", json={})).status_code == 404


async def test_module_assignment_and_unassignment(api):
    client, _ = api
    await _import(client)
    alpha = await _subject(client, "Alpha")
    module = (await client.post("/api/modules", json={"name": "M"})).json()
    assert module["subject_id"] is None
    resp = await client.patch(f"/api/modules/{module['id']}", json={"subject_id": alpha["id"]})
    assert resp.json()["subject_id"] == alpha["id"]
    assert (await client.get(f"/api/subjects/{alpha['id']}")).json()["module_ids"] == [module["id"]]
    resp = await client.patch(f"/api/modules/{module['id']}", json={"name": "M2"})
    assert resp.json()["subject_id"] == alpha["id"]
    resp = await client.patch(f"/api/modules/{module['id']}", json={"subject_id": None})
    assert resp.json()["subject_id"] is None
    assert (await client.get(f"/api/subjects/{alpha['id']}")).json()["module_ids"] == []
    resp = await client.patch(f"/api/modules/{module['id']}", json={"subject_id": 999})
    assert resp.status_code == 404


async def test_attempt_rules(api):
    client, app = api
    _today(app, 2027, 2, 10)
    await _import(client)
    alpha = await _subject(client, "Alpha")
    url = f"/api/subjects/{alpha['id']}/attempts"

    resp = await client.post(url, json={"sitting": "2027-04-01", "status": "planned"})
    assert resp.status_code == 422
    resp = await client.post(url, json={"sitting": "2027-03-10", "status": "passed"})
    assert resp.status_code == 422
    assert (
        await client.post(
            "/api/subjects/999/attempts", json={"sitting": "2027-03-10", "status": "planned"}
        )
    ).status_code == 404

    planned = (await client.post(url, json={"sitting": "2027-03-10", "status": "planned"})).json()
    assert planned["status"] == "planned"
    registered = (
        await client.post(url, json={"sitting": "2027-03-10", "status": "registered"})
    ).json()
    attempts = (await client.get(f"/api/subjects/{alpha['id']}")).json()["attempts"]
    assert [(a["id"], a["status"]) for a in attempts] == [(registered["id"], "registered")]

    resp = await client.patch(f"/api/attempts/{registered['id']}", json={"status": "passed"})
    assert resp.status_code == 409
    resp = await client.patch(f"/api/attempts/{registered['id']}", json={"status": "planned"})
    assert resp.json()["status"] == "planned"

    _today(app, 2027, 3, 10)
    resp = await client.patch(f"/api/attempts/{registered['id']}", json={"status": "failed"})
    assert resp.json()["status"] == "failed"
    assert (await client.delete(f"/api/attempts/{registered['id']}")).status_code == 409
    assert (await client.patch("/api/attempts/999", json={"status": "failed"})).status_code == 404
    assert (await client.delete("/api/attempts/999")).status_code == 404

    again = (await client.post(url, json={"sitting": "2027-03-10", "status": "planned"})).json()
    attempts = (await client.get(f"/api/subjects/{alpha['id']}")).json()["attempts"]
    assert sorted(a["status"] for a in attempts) == ["failed", "planned"]
    assert (await client.delete(f"/api/attempts/{again['id']}")).status_code == 204
    attempts = (await client.get(f"/api/subjects/{alpha['id']}")).json()["attempts"]
    assert [a["status"] for a in attempts] == ["failed"]
