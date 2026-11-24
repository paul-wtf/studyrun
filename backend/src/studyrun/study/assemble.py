from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fsrs import State
from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.clock import local_day_bounds
from studyrun.config import Settings
from studyrun.models.db import (
    Booklet,
    Chapter,
    ChapterStatus,
    Item,
    ItemKind,
    ItemStatus,
    Module,
    ReviewState,
)

RunEntry = dict[str, Any]


@dataclass(frozen=True)
class _Pick:
    item_id: int
    chapter_id: int
    kind: ItemKind


_ACTIVE_READY = (Item.status == ItemStatus.active, Chapter.status == ChapterStatus.ready)
_LEARNING = (State.Learning.value, State.Relearning.value)


def _select_picks() -> Any:
    return select(Item.id, Item.chapter_id, Item.kind).join(Chapter, Chapter.id == Item.chapter_id)


def _picks(rows: Any) -> list[_Pick]:
    return [_Pick(item_id, chapter_id, kind) for item_id, chapter_id, kind in rows]


def _rotate_kinds(picks: list[_Pick]) -> list[_Pick]:
    chapters: dict[int, dict[ItemKind, list[_Pick]]] = {}
    for pick in picks:
        chapters.setdefault(pick.chapter_id, {}).setdefault(pick.kind, []).append(pick)
    ordered: list[_Pick] = []
    for by_kind in chapters.values():
        queues = list(by_kind.values())
        while queues:
            ordered += [queue.pop(0) for queue in queues]
            queues = [queue for queue in queues if queue]
    return ordered


async def _due_items(session: AsyncSession, cutoff: datetime, limit: int | None) -> list[_Pick]:
    learning = ReviewState.card["state"].astext.cast(Integer).in_(_LEARNING)
    stmt = (
        _select_picks()
        .join(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.due < cutoff)
        .order_by(case((learning, 0), else_=1), ReviewState.due, Item.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return _picks((await session.execute(stmt)).all())


async def _due_count(session: AsyncSession, cutoff: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(Item)
        .join(Chapter, Chapter.id == Item.chapter_id)
        .join(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.due < cutoff)
    )
    return await session.scalar(stmt) or 0


async def _unseen_items(
    session: AsyncSession, *, module_id: int | None, chapter_id: int | None, introduced: bool
) -> list[_Pick]:
    stmt = (
        _select_picks()
        .outerjoin(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.item_id.is_(None))
        .order_by(Chapter.index, Chapter.id, Item.id)
    )
    if introduced:
        stmt = stmt.where(Chapter.introduced_at.is_not(None))
    if chapter_id is not None:
        stmt = stmt.where(Chapter.id == chapter_id)
    if module_id is not None:
        stmt = stmt.join(Booklet, Booklet.id == Chapter.booklet_id).where(
            Booklet.module_id == module_id
        )
    return _rotate_kinds(_picks((await session.execute(stmt)).all()))


async def _focus(session: AsyncSession) -> tuple[int, Chapter | None] | None:
    modules = (await session.scalars(select(Module).order_by(Module.position, Module.id))).all()
    for module in modules:
        unseen = await _unseen_items(session, module_id=module.id, chapter_id=None, introduced=True)
        next_chapter = (
            await session.scalars(
                select(Chapter)
                .join(Booklet, Booklet.id == Chapter.booklet_id)
                .where(
                    Booklet.module_id == module.id,
                    Chapter.status == ChapterStatus.ready,
                    Chapter.introduced_at.is_(None),
                )
                .order_by(Chapter.index, Chapter.id)
                .limit(1)
            )
        ).first()
        if unseen or next_chapter:
            return module.id, next_chapter
    return None


def _interleave(picks: list[_Pick]) -> list[_Pick]:
    remaining = list(picks)
    ordered: list[_Pick] = []
    while remaining:
        prev = ordered[-1] if ordered else None
        choice = remaining[0]
        if prev is not None:
            best = (
                [p for p in remaining if p.kind != prev.kind and p.chapter_id != prev.chapter_id]
                or [p for p in remaining if p.kind != prev.kind]
                or [p for p in remaining if p.chapter_id != prev.chapter_id]
            )
            choice = best[0] if best else remaining[0]
        remaining.remove(choice)
        ordered.append(choice)
    return ordered


async def build_run(session: AsyncSession, settings: Settings, now: datetime) -> list[RunEntry]:
    _, cutoff = local_day_bounds(now, settings.timezone)
    picks = await _due_items(session, cutoff, settings.run_review_cap)
    intro_chapter_id: int | None = None
    intake = await _due_count(session, cutoff) <= settings.run_review_cap

    focus = await _focus(session) if intake else None
    if focus is not None:
        module_id, next_chapter = focus
        taken = {p.item_id for p in picks}
        new = [
            p
            for p in await _unseen_items(
                session, module_id=module_id, chapter_id=None, introduced=True
            )
            if p.item_id not in taken
        ][: settings.run_new_items]
        if len(new) < settings.run_new_items and next_chapter is not None:
            intro_chapter_id = next_chapter.id
            fresh = await _unseen_items(
                session, module_id=None, chapter_id=next_chapter.id, introduced=False
            )
            new += fresh[: settings.run_new_items - len(new)]
        picks += new

    if not any(p.kind == ItemKind.free for p in picks):
        taken = {p.item_id for p in picks}
        free = [
            p
            for p in await _due_items(session, cutoff, None)
            if p.kind == ItemKind.free and p.item_id not in taken
        ]
        if not free and intake:
            unseen = await _unseen_items(session, module_id=None, chapter_id=None, introduced=True)
            if intro_chapter_id is not None:
                unseen += await _unseen_items(
                    session, module_id=None, chapter_id=intro_chapter_id, introduced=False
                )
            free = [p for p in unseen if p.kind == ItemKind.free and p.item_id not in taken]
        if free:
            picks.append(free[0])

    entries: list[RunEntry] = []
    intro_pending = intro_chapter_id
    for pick in _interleave(picks):
        if intro_pending is not None and pick.chapter_id == intro_pending:
            entries.append({"type": "intro", "chapter_id": intro_pending})
            intro_pending = None
        entries.append({"type": "item", "item_id": pick.item_id})
    if intro_pending is not None:
        entries.append({"type": "intro", "chapter_id": intro_pending})
    return entries
