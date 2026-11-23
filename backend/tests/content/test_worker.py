import asyncio
from datetime import datetime

import pytest
from builders import content, mc, seed_booklet, seed_chapter, seed_module, verdicts
from fakes import FakeBatchLLM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from studyrun.config import Settings
from studyrun.content import worker
from studyrun.content.worker import run_worker, tick
from studyrun.models.db import Chapter, ChapterStatus

NOW = datetime.fromisoformat("2026-11-23T12:00:00+01:00")


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


async def _statuses(session) -> dict[int, ChapterStatus]:
    rows = await session.execute(
        select(Chapter.id, Chapter.status).execution_options(populate_existing=True)
    )
    return {chapter_id: status for chapter_id, status in rows}


async def test_worker_respects_max_in_flight(db_session, factory):
    module = await seed_module(db_session)
    booklet = await seed_booklet(db_session, module)
    for index in range(5):
        await seed_chapter(db_session, booklet, index=index)
    llm = FakeBatchLLM()

    await tick(factory, llm, Settings(), NOW)
    statuses = list((await _statuses(db_session)).values())
    assert statuses.count(ChapterStatus.generating) == 3
    assert statuses.count(ChapterStatus.pending) == 2
    assert len(llm.submits) == 3

    await tick(factory, llm, Settings(), NOW)
    assert len(llm.submits) == 3
    assert len(llm.collects) == 3


async def test_worker_submits_next_when_a_batch_finishes(db_session, factory):
    module = await seed_module(db_session)
    booklet = await seed_booklet(db_session, module)
    chapters = [await seed_chapter(db_session, booklet, index=i) for i in range(4)]
    settings = Settings(generation_max_in_flight=2)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapters[0].id}", content([mc()]))
    llm.queue(f"ver-{chapters[0].id}", verdicts(True))

    await tick(factory, llm, settings, NOW)
    await tick(factory, llm, settings, NOW)
    assert len(llm.submits) == 3
    await tick(factory, llm, settings, NOW)
    statuses = await _statuses(db_session)
    assert statuses[chapters[0].id] == ChapterStatus.ready
    assert statuses[chapters[2].id] == ChapterStatus.generating
    assert statuses[chapters[3].id] == ChapterStatus.pending


async def test_worker_order(db_session, factory):
    later = await seed_module(db_session, position=2, name="Später")
    first = await seed_module(db_session, position=1, name="Zuerst")
    late_booklet = await seed_booklet(db_session, later)
    booklet_a = await seed_booklet(db_session, first)
    booklet_b = await seed_booklet(db_session, first)
    expected = [
        await seed_chapter(db_session, booklet_b, index=0),
        await seed_chapter(db_session, late_booklet, index=1),
        await seed_chapter(db_session, booklet_a, index=1),
        await seed_chapter(db_session, late_booklet, index=0),
        await seed_chapter(db_session, booklet_a, index=0),
    ]
    order = [expected[i] for i in (4, 2, 0, 3, 1)]
    llm = FakeBatchLLM()

    await tick(factory, llm, Settings(generation_max_in_flight=10), NOW)
    assert [c.custom_id for c in llm.submits] == [f"gen-{c.id}" for c in order]


async def test_worker_skips_waiting_until_next_day(db_session, factory):
    module = await seed_module(db_session)
    booklet = await seed_booklet(db_session, module)
    chapter = await seed_chapter(
        db_session,
        booklet,
        waiting_reason="Tagesbudget für die Erzeugung erreicht",
        waiting_since=datetime.fromisoformat("2026-11-23T23:30:00+00:00"),
    )
    llm = FakeBatchLLM()

    await tick(factory, llm, Settings(), datetime.fromisoformat("2026-11-24T20:00:00+01:00"))
    assert llm.submits == []

    await tick(factory, llm, Settings(), datetime.fromisoformat("2026-11-25T00:10:00+01:00"))
    assert [c.custom_id for c in llm.submits] == [f"gen-{chapter.id}"]
    refreshed = await db_session.get(Chapter, chapter.id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.status == ChapterStatus.generating
    assert refreshed.waiting_reason is None


async def test_restart_resumes_from_batch_id(db_session, factory):
    module = await seed_module(db_session)
    booklet = await seed_booklet(db_session, module)
    draft = content([mc(), mc(prompt="Wie heißt der erfundene Testfluss?")])
    chapter = await seed_chapter(
        db_session,
        booklet,
        status=ChapterStatus.verifying,
        batch_id="msgbatch_before_restart",
        draft=draft.model_dump(mode="json"),
    )
    llm = FakeBatchLLM([verdicts(False, True)])

    await tick(factory, llm, Settings(), NOW)
    assert [c.batch_id for c in llm.collects] == ["msgbatch_before_restart"]
    assert llm.submits == []
    refreshed = await db_session.get(Chapter, chapter.id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.status == ChapterStatus.ready
    assert refreshed.summary == draft.summary


async def test_run_worker_ticks_until_stopped(db_session, factory):
    module = await seed_module(db_session)
    booklet = await seed_booklet(db_session, module)
    await seed_chapter(db_session, booklet)
    llm = FakeBatchLLM()
    stop = asyncio.Event()

    task = asyncio.create_task(
        run_worker(factory, llm, stop, poll_seconds=0.01, settings=Settings(), clock=lambda: NOW)
    )
    while len(llm.collects) < 2:
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert len(llm.submits) == 1


async def test_run_worker_survives_a_failing_tick(monkeypatch, factory):
    calls = 0
    stop = asyncio.Event()

    async def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Datenbank weg")
        stop.set()

    monkeypatch.setattr(worker, "tick", flaky)
    await asyncio.wait_for(
        run_worker(factory, FakeBatchLLM(), stop, poll_seconds=0.01, settings=Settings()),
        timeout=2,
    )
    assert calls == 2


async def _run_lifespan(monkeypatch, enabled: bool) -> list[str]:
    from studyrun import main
    from studyrun.deps import get_settings

    events: list[str] = []

    async def fake_worker(factory, llm, stop, *args, **kwargs):
        events.append("started")
        await stop.wait()
        events.append("stopped")

    monkeypatch.setenv("STUDYRUN_WORKER_ENABLED", "true" if enabled else "false")
    monkeypatch.setattr(main, "run_worker", fake_worker)
    monkeypatch.setattr(main, "AnthropicLLM", lambda settings: object())
    get_settings.cache_clear()
    try:
        app = main.create_app()
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)
            events.append("serving")
    finally:
        get_settings.cache_clear()
    return events


async def test_lifespan_runs_the_worker(monkeypatch):
    assert await _run_lifespan(monkeypatch, True) == ["started", "serving", "stopped"]


async def test_lifespan_skips_the_worker_when_disabled(monkeypatch):
    assert await _run_lifespan(monkeypatch, False) == ["serving"]
