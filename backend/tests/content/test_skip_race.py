import asyncio
from datetime import datetime

import pytest
from builders import seed_booklet, seed_chapter, seed_module
from fakes import FakeBatchLLM
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from studyrun.content.pipeline import advance_chapter
from studyrun.models.db import Chapter, ChapterStatus, Module
from studyrun.routes.booklets import skip_chapter

NOW = datetime.fromisoformat("2026-11-23T12:00:00+01:00")


@pytest.fixture
async def committed(_engine):
    factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with factory() as session:
        module = await seed_module(session)
        booklet = await seed_booklet(session, module)
        chapter = await seed_chapter(session, booklet)
        await session.commit()
    try:
        yield factory, chapter.id
    finally:
        async with factory() as session:
            await session.execute(delete(Module).where(Module.id == module.id))
            await session.commit()


async def test_skip_loses_against_a_worker_that_submitted_first(committed):
    factory, chapter_id = committed
    llm = FakeBatchLLM()

    async def skip() -> None:
        async with factory() as session:
            await skip_chapter(chapter_id, session)
            await session.commit()

    async with factory() as worker:
        await advance_chapter(worker, llm, chapter_id, NOW)
        skipping = asyncio.create_task(skip())
        await asyncio.sleep(0.3)
        await worker.commit()

    with pytest.raises(HTTPException) as raised:
        await skipping
    assert raised.value.status_code == 409
    async with factory() as session:
        chapter = await session.get(Chapter, chapter_id)
        assert chapter is not None
        assert chapter.status == ChapterStatus.generating
        assert chapter.batch_id == llm.submits[0].batch_id
