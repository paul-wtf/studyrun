import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testdb import derive_test_url, ensure_database

from studyrun.db import Base

TEST_DB_URL = derive_test_url(
    os.environ.get(
        "STUDYRUN_TEST_DATABASE_URL",
        "postgresql+asyncpg://studyrun:studyrun@localhost:5432/studyrun",
    )
)


@pytest.fixture(autouse=True)
def _isolate_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest_asyncio.fixture(scope="session")
async def test_database() -> str:
    await ensure_database(TEST_DB_URL)
    return TEST_DB_URL


@pytest_asyncio.fixture(scope="session")
async def _engine(test_database):
    engine = create_async_engine(test_database, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    connection = await _engine.connect()
    trans = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def api(db_session, monkeypatch):
    monkeypatch.setenv("STUDYRUN_DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("STUDYRUN_WORKER_ENABLED", "false")
    from studyrun.deps import get_session, get_settings
    from studyrun.main import create_app

    get_settings.cache_clear()
    app = create_app()

    async def _use_test_session():
        yield db_session

    app.dependency_overrides[get_session] = _use_test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    get_settings.cache_clear()
