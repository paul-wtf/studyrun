from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fsrs import State
from sqlalchemy import Integer, and_, case, func, or_, select
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
    MockExam,
    Module,
    ReviewState,
    Run,
    Subject,
)
from studyrun.planning import current_plan, local_today
from studyrun.planning.planner import REGISTRATION_DAYS

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


Groups = Sequence[int | None]


def _subject_filter(groups: Groups) -> Any:
    subject_ids = [g for g in groups if g is not None]
    return or_(
        Module.subject_id.in_(subject_ids),
        *([Module.subject_id.is_(None)] if None in groups else []),
    )


def _in_groups(stmt: Any, groups: Groups | None) -> Any:
    if groups is None:
        return stmt
    return (
        stmt.join(Booklet, Booklet.id == Chapter.booklet_id)
        .join(Module, Module.id == Booklet.module_id)
        .where(_subject_filter(groups))
    )


def _not_blocked(stmt: Any, blocked: frozenset[int]) -> Any:
    return stmt.where(Item.id.not_in(blocked)) if blocked else stmt


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


async def _due_items(
    session: AsyncSession,
    cutoff: datetime,
    limit: int | None,
    scope: Groups | None,
    blocked: frozenset[int] = frozenset(),
) -> list[_Pick]:
    learning = ReviewState.card["state"].astext.cast(Integer).in_(_LEARNING)
    stmt = (
        _not_blocked(_in_groups(_select_picks(), scope), blocked)
        .join(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.due < cutoff)
        .order_by(case((learning, 0), else_=1), ReviewState.due, Item.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return _picks((await session.execute(stmt)).all())


async def _due_count(session: AsyncSession, cutoff: datetime, scope: Groups | None) -> int:
    stmt = (
        _in_groups(
            select(func.count()).select_from(Item).join(Chapter, Chapter.id == Item.chapter_id),
            scope,
        )
        .join(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.due < cutoff)
    )
    return await session.scalar(stmt) or 0


async def _upcoming_items(
    session: AsyncSession,
    cutoff: datetime,
    windows: Sequence[tuple[int, datetime | None]],
    limit: int,
    blocked: frozenset[int],
) -> list[_Pick]:
    in_window = [
        Module.subject_id == subject_id
        if until is None
        else and_(Module.subject_id == subject_id, ReviewState.due < until)
        for subject_id, until in windows
    ]
    stmt = (
        _not_blocked(_select_picks(), blocked)
        .join(Booklet, Booklet.id == Chapter.booklet_id)
        .join(Module, Module.id == Booklet.module_id)
        .join(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.due >= cutoff, or_(*in_window))
        .order_by(ReviewState.due, Item.id)
        .limit(limit)
    )
    return _picks((await session.execute(stmt)).all())


async def _unseen_items(
    session: AsyncSession,
    *,
    module_id: int | None,
    chapter_id: int | None,
    introduced: bool,
    scope: Groups | None = None,
) -> list[_Pick]:
    stmt = (
        _in_groups(_select_picks(), scope)
        .outerjoin(ReviewState, ReviewState.item_id == Item.id)
        .where(*_ACTIVE_READY, ReviewState.item_id.is_(None))
        .order_by(Chapter.index, Chapter.id, Item.id)
    )
    if introduced:
        stmt = stmt.where(Chapter.introduced_at.is_not(None))
    if chapter_id is not None:
        stmt = stmt.where(Chapter.id == chapter_id)
    if module_id is not None:
        stmt = stmt.where(
            Chapter.booklet_id.in_(select(Booklet.id).where(Booklet.module_id == module_id))
        )
    return _rotate_kinds(_picks((await session.execute(stmt)).all()))


async def _modules(session: AsyncSession, group: int | None) -> Sequence[Module]:
    return (
        await session.scalars(
            select(Module).where(_subject_filter([group])).order_by(Module.position, Module.id)
        )
    ).all()


async def _module_focus(
    session: AsyncSession, modules: Sequence[Module]
) -> tuple[int, Chapter | None] | None:
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


async def _focus(session: AsyncSession, groups: Groups) -> tuple[int, Chapter | None] | None:
    for group in groups:
        focus = await _module_focus(session, await _modules(session, group))
        if focus is not None:
            return focus
    return None


def _day_end(day: date, tz: str) -> datetime:
    return datetime.combine(day + timedelta(days=1), time(), ZoneInfo(tz)).astimezone(UTC)


async def _daily_plan(
    session: AsyncSession, settings: Settings, now: datetime
) -> tuple[list[int | None], list[tuple[int, datetime | None]]]:
    if not await session.scalar(select(select(Subject.id).exists())):
        return [None], []
    current = await current_plan(session, settings, now)
    today = local_today(settings, now)
    states = {entry.subject_id: entry.state for entry in current.plan.entries}
    rest = sorted(
        (
            s
            for s in current.subjects
            if s.id not in current.plan.order and states[s.id] not in ("passed", "needs_result")
        ),
        key=lambda s: (s.recommended_semester is None, s.recommended_semester or 0, s.name, s.id),
    )
    windows: list[tuple[int, datetime | None]] = [
        (entry.subject_id, _day_end(entry.sitting, settings.timezone))
        for entry in current.plan.entries
        if entry.state in ("planned", "registered")
        and entry.sitting is not None
        and today <= entry.sitting <= today + timedelta(days=REGISTRATION_DAYS)
    ]
    return [*current.plan.order, *(s.id for s in rest), None], windows


async def open_items(session: AsyncSession, settings: Settings, now: datetime) -> frozenset[int]:
    runs = await session.scalars(
        select(Run).where(Run.finished_at.is_(None), Run.local_date == local_today(settings, now))
    )
    mocks = await session.scalars(
        select(MockExam.entries).where(MockExam.finished_at.is_(None), MockExam.deadline > now)
    )
    return frozenset(
        entry["item_id"]
        for run in runs
        for entry in run.entries
        if entry["type"] == "item" and not entry.get("done")
    ) | frozenset(entry["item_id"] for entries in mocks for entry in entries)


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


async def build_run(
    session: AsyncSession, settings: Settings, now: datetime, *, subject_id: int | None = None
) -> list[RunEntry]:
    _, cutoff = local_day_bounds(now, settings.timezone)
    groups: Groups
    if subject_id is None:
        groups, windows = await _daily_plan(session, settings, now)
        scope: Groups | None = None
    else:
        groups, windows = [subject_id], [(subject_id, None)]
        scope = groups
    blocked = await open_items(session, settings, now)
    picks = await _due_items(session, cutoff, settings.run_review_cap, scope, blocked)
    intro_chapter_id: int | None = None
    intake = await _due_count(session, cutoff, scope) <= settings.run_review_cap

    room = settings.run_review_cap - len(picks)
    if windows and room > 0:
        picks += await _upcoming_items(session, cutoff, windows, room, blocked)

    focus = await _focus(session, groups) if intake else None
    if focus is not None:
        module_id, next_chapter = focus
        taken = blocked | {p.item_id for p in picks}
        new = [
            p
            for p in await _unseen_items(
                session, module_id=module_id, chapter_id=None, introduced=True
            )
            if p.item_id not in taken
        ][: settings.run_new_items]
        if len(new) < settings.run_new_items and next_chapter is not None:
            intro_chapter_id = next_chapter.id
            fresh = [
                p
                for p in await _unseen_items(
                    session, module_id=None, chapter_id=next_chapter.id, introduced=False
                )
                if p.item_id not in taken
            ]
            new += fresh[: settings.run_new_items - len(new)]
        picks += new

    if not any(p.kind == ItemKind.free for p in picks):
        taken = blocked | {p.item_id for p in picks}
        free = [
            p
            for p in await _due_items(session, cutoff, None, scope)
            if p.kind == ItemKind.free and p.item_id not in taken
        ]
        if not free and intake:
            unseen = await _unseen_items(
                session, module_id=None, chapter_id=None, introduced=True, scope=groups
            )
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
