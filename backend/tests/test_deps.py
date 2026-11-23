from contextlib import asynccontextmanager

import httpx

from studyrun.deps import get_session


async def test_a_failing_commit_is_a_server_error(api, db_session):
    _, app = api

    async def refuse() -> None:
        raise RuntimeError("commit refused")

    @asynccontextmanager
    async def factory():
        yield db_session

    db_session.commit = refuse
    app.state.session_factory = factory
    del app.dependency_overrides[get_session]
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/modules", json={"name": "M"})
    assert resp.status_code == 500
