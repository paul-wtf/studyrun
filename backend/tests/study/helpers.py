from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fsrs import Card, State
from sqlalchemy.ext.asyncio import AsyncSession

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


def _card(due: datetime, state: State) -> Card:
    if state == State.Review:
        return Card(
            state=state,
            step=None,
            stability=10.0,
            difficulty=5.0,
            due=due,
            last_review=due - timedelta(days=10),
        )
    return Card(
        state=state,
        step=0,
        stability=2.0,
        difficulty=5.0,
        due=due,
        last_review=due - timedelta(minutes=10),
    )


async def make_module(session: AsyncSession, position: int = 0) -> Module:
    module = Module(name=f"Modul {position}", position=position)
    session.add(module)
    await session.flush()
    return module


async def make_chapter(
    session: AsyncSession,
    module: Module,
    index: int = 0,
    *,
    status: ChapterStatus = ChapterStatus.ready,
    introduced_at: datetime | None = None,
) -> Chapter:
    booklet = Booklet(module_id=module.id, filename="b.pdf", pdf=b"", page_count=10)
    session.add(booklet)
    await session.flush()
    chapter = Chapter(
        booklet_id=booklet.id,
        index=index,
        title=f"Kapitel {index}",
        first_page=1,
        last_page=10,
        status=status,
        introduced_at=introduced_at,
    )
    session.add(chapter)
    await session.flush()
    return chapter


async def make_item(
    session: AsyncSession,
    chapter: Chapter,
    kind: ItemKind = ItemKind.mc,
    *,
    status: ItemStatus = ItemStatus.active,
    due: datetime | None = None,
    state: State = State.Review,
    payload: dict[str, Any] | None = None,
) -> Item:
    item = Item(
        chapter_id=chapter.id, kind=kind, payload=payload or {}, source_page=1, status=status
    )
    session.add(item)
    await session.flush()
    if due is not None:
        session.add(
            ReviewState(
                item_id=item.id, card=_card(due, state).to_dict(), due=due, last_review=None
            )
        )
        await session.flush()
    return item
