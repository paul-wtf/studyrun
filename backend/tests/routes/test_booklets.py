import pytest
from content.pdfs import build_pdf
from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from studyrun.deps import get_settings
from studyrun.models.db import Chapter, ChapterStatus


async def _module(client):
    return (await client.post("/api/modules", json={"name": "M"})).json()["id"]


def _files(data, name="heft.pdf"):
    return {"file": (name, data, "application/pdf")}


async def test_upload_creates_pending_chapters(api):
    client, _ = api
    module_id = await _module(client)
    data = build_pdf(12, outline=[("Grundlagen", 1), ("Vertiefung", 6)])
    resp = await client.post(f"/api/modules/{module_id}/booklets", files=_files(data))
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "heft.pdf"
    assert body["page_count"] == 12
    assert body["status"] == "processing"
    assert body["chapters"] == {
        "pending": 2,
        "generating": 0,
        "verifying": 0,
        "ready": 0,
        "failed": 0,
    }

    chapters = (await client.get(f"/api/modules/{module_id}/chapters")).json()
    assert [(c["title"], c["first_page"], c["last_page"], c["status"]) for c in chapters] == [
        ("Grundlagen", 1, 5, "pending"),
        ("Vertiefung", 6, 12, "pending"),
    ]
    assert chapters[0]["active_items"] == 0
    assert chapters[0]["error"] is None

    listing = (await client.get("/api/modules")).json()
    assert listing[0]["booklets"][0]["id"] == body["id"]
    assert listing[0]["booklets"][0]["chapters"]["pending"] == 2


async def test_upload_to_unknown_module(api):
    client, _ = api
    resp = await client.post("/api/modules/999/booklets", files=_files(build_pdf(3)))
    assert resp.status_code == 404


async def test_upload_needs_confirmation(api):
    client, _ = api
    module_id = await _module(client)
    url = f"/api/modules/{module_id}/booklets"

    resp = await client.post(url, files=_files(build_pdf(250)))
    assert resp.status_code == 409
    assert resp.json() == {"needs_confirmation": True, "estimate_usd": 6.25}
    assert (await client.get(f"/api/modules/{module_id}/chapters")).json() == []

    resp = await client.post(url, files=_files(build_pdf(250)), data={"confirm": "true"})
    assert resp.status_code == 201

    other = await _module(client)
    resp = await client.post(f"/api/modules/{other}/booklets", files=_files(build_pdf(200)))
    assert resp.status_code == 201


async def test_upload_rejects_too_large(api):
    client, app = api
    settings = get_settings().model_copy(update={"upload_max_bytes": 1000})
    app.dependency_overrides[get_settings] = lambda: settings
    module_id = await _module(client)
    resp = await client.post(f"/api/modules/{module_id}/booklets", files=_files(build_pdf(3)))
    assert resp.status_code == 413


async def test_upload_rejects_non_pdf_with_german_message(api):
    client, _ = api
    module_id = await _module(client)
    resp = await client.post(
        f"/api/modules/{module_id}/booklets", files=_files(b"das ist kein pdf")
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail


async def test_pdf_download(api):
    client, _ = api
    module_id = await _module(client)
    data = build_pdf(3)
    booklet = (await client.post(f"/api/modules/{module_id}/booklets", files=_files(data))).json()
    resp = await client.get(f"/api/booklets/{booklet['id']}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.content == data
    assert (await client.get("/api/booklets/999/pdf")).status_code == 404


async def test_pdf_download_in_a_fresh_session(api, db_session):
    client, _ = api
    module_id = await _module(client)
    data = build_pdf(3)
    booklet = (await client.post(f"/api/modules/{module_id}/booklets", files=_files(data))).json()
    db_session.expunge_all()
    resp = await client.get(f"/api/booklets/{booklet['id']}/pdf")
    assert resp.status_code == 200
    assert resp.content == data


async def test_module_listing_does_not_load_pdf_bytes(api, db_session):
    client, _ = api
    module_id = await _module(client)
    await client.post(f"/api/modules/{module_id}/booklets", files=_files(build_pdf(3)))
    db_session.expunge_all()
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        assert (await client.get("/api/modules")).status_code == 200
        assert (await client.get(f"/api/modules/{module_id}/chapters")).status_code == 200
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert any("FROM booklets" in s for s in statements)
    assert not any("booklets.pdf" in s for s in statements)


async def _first_chapter(client, db_session):
    module_id = await _module(client)
    await client.post(f"/api/modules/{module_id}/booklets", files=_files(build_pdf(3)))
    return (await db_session.scalars(select(Chapter))).one()


async def test_retry_failed_chapter(api, db_session):
    client, _ = api
    chapter = await _first_chapter(client, db_session)
    chapter.status = ChapterStatus.failed
    chapter.error = "kaputt"
    chapter.batch_id = "b1"
    chapter.draft = {"x": 1}
    chapter.waiting_reason = "budget"
    await db_session.flush()

    resp = await client.post(f"/api/chapters/{chapter.id}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"
    await db_session.refresh(chapter)
    assert chapter.status == ChapterStatus.pending
    assert chapter.error is None
    assert chapter.batch_id is None
    assert chapter.draft is None
    assert chapter.waiting_reason is None
    assert chapter.waiting_since is None


async def test_retry_ready_chapter_conflicts(api, db_session):
    client, _ = api
    chapter = await _first_chapter(client, db_session)
    chapter.status = ChapterStatus.ready
    await db_session.flush()
    assert (await client.post(f"/api/chapters/{chapter.id}/retry")).status_code == 409
    assert (await client.post("/api/chapters/999/retry")).status_code == 404


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([ChapterStatus.ready, ChapterStatus.ready], "ready"),
        ([ChapterStatus.ready, ChapterStatus.failed, ChapterStatus.pending], "failed"),
        ([ChapterStatus.ready, ChapterStatus.generating], "processing"),
    ],
)
async def test_booklet_status_is_derived(api, db_session, statuses, expected):
    client, _ = api
    module_id = await _module(client)
    data = build_pdf(6, outline=[("A", 1), ("B", 3), ("C", 5)][: len(statuses)])
    await client.post(f"/api/modules/{module_id}/booklets", files=_files(data))
    chapters = (await db_session.scalars(select(Chapter).order_by(Chapter.index))).all()
    for chapter, status in zip(chapters, statuses, strict=True):
        chapter.status = status
    await db_session.flush()
    listing = (await client.get("/api/modules")).json()
    assert listing[0]["booklets"][0]["status"] == expected
