from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.deps import get_session
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Item, ItemStatus, Module, Subject

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session, scope="function")]


class ChapterCounts(BaseModel):
    pending: int = 0
    generating: int = 0
    verifying: int = 0
    ready: int = 0
    failed: int = 0
    skipped: int = 0


BookletStatus = Literal["processing", "ready", "failed"]


class BookletOut(BaseModel):
    id: int
    filename: str
    page_count: int
    status: BookletStatus
    chapters: ChapterCounts


class ModuleOut(BaseModel):
    id: int
    name: str
    position: int
    subject_id: int | None
    booklets: list[BookletOut]


class ModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ModulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    position: int | None = Field(default=None, ge=0)
    subject_id: int | None = None


class ChapterOut(BaseModel):
    id: int
    booklet_id: int
    index: int
    title: str
    first_page: int
    last_page: int
    status: ChapterStatus
    error: str | None
    waiting_reason: str | None
    active_items: int


def derive_status(counts: ChapterCounts) -> BookletStatus:
    if counts.failed:
        return "failed"
    done = counts.ready + counts.skipped
    if done and sum(counts.model_dump().values()) == done:
        return "ready"
    return "processing"


async def booklets_out(session: AsyncSession, booklet_ids: list[int]) -> dict[int, BookletOut]:
    if not booklet_ids:
        return {}
    booklets = (await session.scalars(select(Booklet).where(Booklet.id.in_(booklet_ids)))).all()
    rows = await session.execute(
        select(Chapter.booklet_id, Chapter.status, func.count())
        .where(Chapter.booklet_id.in_(booklet_ids))
        .group_by(Chapter.booklet_id, Chapter.status)
    )
    counts = {b.id: ChapterCounts() for b in booklets}
    for booklet_id, status, n in rows:
        setattr(counts[booklet_id], ChapterStatus(status).value, n)
    return {
        b.id: BookletOut(
            id=b.id,
            filename=b.filename,
            page_count=b.page_count,
            status=derive_status(counts[b.id]),
            chapters=counts[b.id],
        )
        for b in booklets
    }


async def module_out(session: AsyncSession, module: Module) -> ModuleOut:
    ids = list(await session.scalars(select(Booklet.id).where(Booklet.module_id == module.id)))
    out = await booklets_out(session, ids)
    return ModuleOut(
        id=module.id,
        name=module.name,
        position=module.position,
        subject_id=module.subject_id,
        booklets=[out[i] for i in sorted(ids)],
    )


async def _get_module(session: AsyncSession, module_id: int) -> Module:
    module = await session.get(Module, module_id)
    if module is None:
        raise HTTPException(404, "Modul nicht gefunden")
    return module


@router.get("/modules")
async def list_modules(session: Session) -> list[ModuleOut]:
    modules = (await session.scalars(select(Module).order_by(Module.position, Module.id))).all()
    booklet_rows = (
        await session.execute(select(Booklet.module_id, Booklet.id).order_by(Booklet.id))
    ).all()
    out = await booklets_out(session, [row[1] for row in booklet_rows])
    return [
        ModuleOut(
            id=m.id,
            name=m.name,
            position=m.position,
            subject_id=m.subject_id,
            booklets=[out[bid] for mid, bid in booklet_rows if mid == m.id],
        )
        for m in modules
    ]


@router.post("/modules", status_code=201)
async def create_module(body: ModuleCreate, session: Session) -> ModuleOut:
    last = await session.scalar(select(func.max(Module.position)))
    module = Module(name=body.name, position=0 if last is None else last + 1)
    session.add(module)
    await session.flush()
    return await module_out(session, module)


@router.patch("/modules/{module_id}")
async def patch_module(module_id: int, body: ModulePatch, session: Session) -> ModuleOut:
    module = await _get_module(session, module_id)
    if body.name is not None:
        module.name = body.name
    if "subject_id" in body.model_fields_set:
        if body.subject_id is not None and await session.get(Subject, body.subject_id) is None:
            raise HTTPException(404, "Fach nicht gefunden")
        module.subject_id = body.subject_id
    if body.position is not None:
        others = list(
            await session.scalars(
                select(Module).where(Module.id != module.id).order_by(Module.position, Module.id)
            )
        )
        others.insert(min(body.position, len(others)), module)
        for position, entry in enumerate(others):
            entry.position = position
    await session.flush()
    return await module_out(session, module)


@router.get("/modules/{module_id}/chapters")
async def list_chapters(module_id: int, session: Session) -> list[ChapterOut]:
    await _get_module(session, module_id)
    active = (
        select(func.count())
        .where(Item.chapter_id == Chapter.id, Item.status == ItemStatus.active)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Chapter, active)
        .join(Booklet, Booklet.id == Chapter.booklet_id)
        .where(Booklet.module_id == module_id)
        .order_by(Booklet.id, Chapter.index)
    )
    return [chapter_out(chapter, n) for chapter, n in rows]


def chapter_out(chapter: Chapter, active_items: int) -> ChapterOut:
    return ChapterOut(
        id=chapter.id,
        booklet_id=chapter.booklet_id,
        index=chapter.index,
        title=chapter.title,
        first_page=chapter.first_page,
        last_page=chapter.last_page,
        status=chapter.status,
        error=chapter.error,
        waiting_reason=chapter.waiting_reason,
        active_items=active_items,
    )
