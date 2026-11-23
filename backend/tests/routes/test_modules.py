async def _create(client, name):
    resp = await client.post("/api/modules", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def test_create_and_reorder_modules(api):
    client, _ = api
    a = await _create(client, "A")
    b = await _create(client, "B")
    c = await _create(client, "C")
    assert [a["position"], b["position"], c["position"]] == [0, 1, 2]
    assert a["booklets"] == []

    resp = await client.patch(f"/api/modules/{c['id']}", json={"position": 0})
    assert resp.status_code == 200
    listing = (await client.get("/api/modules")).json()
    assert [(m["name"], m["position"]) for m in listing] == [("C", 0), ("A", 1), ("B", 2)]

    resp = await client.patch(f"/api/modules/{c['id']}", json={"position": 2, "name": "C2"})
    assert resp.json()["name"] == "C2"
    listing = (await client.get("/api/modules")).json()
    assert [(m["name"], m["position"]) for m in listing] == [("A", 0), ("B", 1), ("C2", 2)]

    resp = await client.patch(f"/api/modules/{a['id']}", json={"position": 99})
    assert [m["name"] for m in (await client.get("/api/modules")).json()] == ["B", "C2", "A"]


async def test_patch_unknown_module(api):
    client, _ = api
    assert (await client.patch("/api/modules/999", json={"name": "x"})).status_code == 404
