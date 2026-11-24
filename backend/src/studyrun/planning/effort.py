from __future__ import annotations

from fsrs import State
from sqlalchemy import Integer, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.models.db import (
    Booklet,
    Chapter,
    ChapterStatus,
    Item,
    ItemStatus,
    Module,
    ReviewState,
)

ITEMS_PER_PAGE = 2


async def subject_effort(session: AsyncSession, subject_id: int) -> tuple[int, bool]:
    in_subject = (Booklet.module_id == Module.id, Module.subject_id == subject_id)
    has_material = await session.scalar(select(exists().where(*in_subject)))
    state = ReviewState.card["state"].astext.cast(Integer)
    unlearned = await session.scalar(
        select(func.count(Item.id))
        .join(Chapter, Chapter.id == Item.chapter_id)
        .join(Booklet, Booklet.id == Chapter.booklet_id)
        .join(Module, Module.id == Booklet.module_id)
        .outerjoin(ReviewState, ReviewState.item_id == Item.id)
        .where(
            Module.subject_id == subject_id,
            Item.status == ItemStatus.active,
            Chapter.status == ChapterStatus.ready,
            or_(
                ReviewState.item_id.is_(None),
                state.in_([State.Learning.value, State.Relearning.value]),
            ),
        )
    )
    pages = await session.scalar(
        select(func.coalesce(func.sum(Chapter.last_page - Chapter.first_page + 1), 0))
        .join(Booklet, Booklet.id == Chapter.booklet_id)
        .join(Module, Module.id == Booklet.module_id)
        .where(
            Module.subject_id == subject_id,
            Chapter.status.not_in([ChapterStatus.ready, ChapterStatus.skipped]),
        )
    )
    return (unlearned or 0) + ITEMS_PER_PAGE * int(pages or 0), bool(has_material)
