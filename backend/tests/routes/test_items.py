from study.helpers import make_chapter, make_item, make_module

from studyrun.models.db import ItemKind, ItemStatus

MC = {"prompt": "Q?", "options": ["a", "b", "c"], "answer_index": 2, "explanation": "weil c"}
CLOZE = {"text": "Der ___ fliesst.", "answers": ["Strom"], "explanation": "e"}


async def flagged(db_session, kind=ItemKind.mc, payload=MC):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module)
    item = await make_item(db_session, chapter, kind, payload=payload, status=ItemStatus.flagged)
    item.flag_reason = "wrong"
    await db_session.flush()
    return chapter, item


async def test_flag_list(api, db_session):
    client, _ = api
    chapter, item = await flagged(db_session)
    module = await make_module(db_session, 1)
    other = await make_chapter(db_session, module)
    await make_item(db_session, other, payload=MC)
    resp = await client.get("/api/flags")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": item.id,
            "kind": "mc",
            "payload": MC,
            "source_page": 1,
            "reason": "wrong",
            "chapter_title": chapter.title,
            "source": f"/api/booklets/{chapter.booklet_id}/pdf#page=1",
        }
    ]


async def test_fix_reactivates(api, db_session):
    client, _ = api
    _, item = await flagged(db_session)
    fixed = {**MC, "answer_index": 1}
    resp = await client.put(f"/api/items/{item.id}", json={"payload": fixed, "source_page": 4})
    assert resp.status_code == 200
    await db_session.refresh(item)
    assert (item.status, item.flag_reason) == (ItemStatus.active, None)
    assert item.payload == fixed
    assert item.source_page == 4
    assert (await client.get("/api/flags")).json() == []


async def test_fix_keeps_source_page_when_omitted(api, db_session):
    client, _ = api
    _, item = await flagged(db_session)
    resp = await client.put(f"/api/items/{item.id}", json={"payload": MC})
    assert resp.status_code == 200
    await db_session.refresh(item)
    assert item.source_page == 1 and "kind" not in item.payload


async def test_fix_rejects_invalid_payload(api, db_session):
    client, _ = api
    _, item = await flagged(db_session)
    bad = [
        {**MC, "answer_index": 7},
        {**MC, "options": ["a", "A", "c"]},
        {**MC, "options": ["a", "b"]},
        {"prompt": "Q?"},
        {**MC, "prompt": " "},
    ]
    for payload in bad:
        resp = await client.put(f"/api/items/{item.id}", json={"payload": payload})
        assert resp.status_code == 422, payload
        assert resp.json()["detail"].startswith("Ungültige Frage: "), payload
    missing = await client.put(f"/api/items/{item.id}", json={"payload": {"prompt": "Q?"}})
    assert missing.json()["detail"] == (
        "Ungültige Frage: Das Feld »options« fehlt oder ist ungültig."
    )
    resp = await client.put(f"/api/items/{item.id}", json={"payload": MC, "source_page": 99})
    assert resp.status_code == 422
    await db_session.refresh(item)
    assert item.status == ItemStatus.flagged and item.payload == MC


async def test_fix_cloze_needs_one_gap(api, db_session):
    client, _ = api
    _, item = await flagged(db_session, ItemKind.cloze, CLOZE)
    bad = {**CLOZE, "text": "Kein Gap"}
    assert (await client.put(f"/api/items/{item.id}", json={"payload": bad})).status_code == 422
    ok = {**CLOZE, "text": "Der ___ fliesst schnell."}
    assert (await client.put(f"/api/items/{item.id}", json={"payload": ok})).status_code == 200


async def test_fix_unknown_item(api):
    client, _ = api
    assert (await client.put("/api/items/999", json={"payload": MC})).status_code == 404


async def test_delete(api, db_session):
    client, _ = api
    _, item = await flagged(db_session)
    assert (await client.delete(f"/api/items/{item.id}")).status_code == 200
    await db_session.refresh(item)
    assert item.status == ItemStatus.deleted
    assert (await client.get("/api/flags")).json() == []
    assert (await client.delete("/api/items/999")).status_code == 404


async def test_fix_and_delete_only_act_on_flagged_items(api, db_session):
    client, _ = api
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module)
    gone = await make_item(db_session, chapter, payload=MC, status=ItemStatus.deleted)
    live = await make_item(db_session, chapter, payload=MC)
    resp = await client.put(f"/api/items/{gone.id}", json={"payload": MC})
    assert resp.status_code == 409
    await db_session.refresh(gone)
    assert gone.status == ItemStatus.deleted
    assert (await client.put(f"/api/items/{live.id}", json={"payload": MC})).status_code == 409
    assert (await client.delete(f"/api/items/{live.id}")).status_code == 409
    await db_session.refresh(live)
    assert live.status == ItemStatus.active


async def test_delete_twice_conflicts(api, db_session):
    client, _ = api
    _, item = await flagged(db_session)
    assert (await client.delete(f"/api/items/{item.id}")).status_code == 200
    assert (await client.delete(f"/api/items/{item.id}")).status_code == 409
