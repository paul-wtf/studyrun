from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studyrun.ai.clock import local_day_bounds
from studyrun.ai.llm import BatchLLM
from studyrun.config import Settings
from studyrun.content.pipeline import advance_chapter
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Module

log = logging.getLogger(__name__)

Factory = async_sessionmaker[AsyncSession]


def _not_waiting_today(day_start: datetime):
    return or_(Chapter.waiting_since.is_(None), Chapter.waiting_since < day_start)


async def _advance(factory: Factory, llm: BatchLLM, chapter_id: int, now: datetime) -> bool:
    try:
        async with factory() as session:
            await advance_chapter(session, llm, chapter_id, now)
            await session.commit()
            chapter = await session.get(Chapter, chapter_id)
            return chapter is not None and chapter.batch_id is not None
    except Exception:
        log.exception("could not advance chapter %s", chapter_id)
        return False


async def tick(factory: Factory, llm: BatchLLM, settings: Settings, now: datetime) -> None:
    day_start, _ = local_day_bounds(now, settings.timezone)
    async with factory() as session:
        in_progress = (
            await session.scalars(
                select(Chapter.id)
                .where(
                    Chapter.status.in_([ChapterStatus.generating, ChapterStatus.verifying]),
                    or_(Chapter.batch_id.is_not(None), _not_waiting_today(day_start)),
                )
                .order_by(Chapter.id)
            )
        ).all()
    for chapter_id in in_progress:
        await _advance(factory, llm, chapter_id, now)

    async with factory() as session:
        open_batches = await session.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.batch_id.is_not(None))
        )
        pending = (
            await session.scalars(
                select(Chapter.id)
                .join(Booklet, Booklet.id == Chapter.booklet_id)
                .join(Module, Module.id == Booklet.module_id)
                .where(Chapter.status == ChapterStatus.pending, _not_waiting_today(day_start))
                .order_by(Module.position, Booklet.id, Chapter.index)
            )
        ).all()
    in_flight = open_batches or 0
    for chapter_id in pending:
        if in_flight >= settings.generation_max_in_flight:
            break
        if await _advance(factory, llm, chapter_id, now):
            in_flight += 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def run_worker(
    factory: Factory,
    llm: BatchLLM,
    stop: asyncio.Event,
    poll_seconds: float = 60,
    *,
    settings: Settings | None = None,
    clock: Callable[[], datetime] = _utcnow,
) -> None:
    settings = settings or Settings()
    while not stop.is_set():
        try:
            await tick(factory, llm, settings, clock())
        except Exception:
            log.exception("generation worker tick failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
