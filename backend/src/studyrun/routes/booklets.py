from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from studyrun.config import Settings
from studyrun.content.pdf import BookletError, split_booklet
from studyrun.deps import get_settings
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Item, ItemStatus
from studyrun.routes.modules import (
    BookletOut,
    ChapterOut,
    Session,
    _get_module,
    booklets_out,
    chapter_out,
)

router = APIRouter()

CHUNK_BYTES = 1024 * 1024


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, "Die Datei ist zu gross.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/modules/{module_id}/booklets", status_code=201, response_model=BookletOut)
async def upload_booklet(
    module_id: int,
    session: Session,
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    confirm: Annotated[bool, Form()] = False,
):
    await _get_module(session, module_id)
    data = await _read_limited(file, settings.upload_max_bytes)
    try:
        slices = split_booklet(
            data, max_pages=settings.max_chapter_pages, window=settings.chapter_window_pages
        )
    except BookletError as exc:
        raise HTTPException(422, exc.message_de) from exc

    page_count = max(s.last_page for s in slices)
    estimate = round(page_count * settings.generation_estimate_usd_per_page, 2)
    if not confirm and estimate > settings.generation_confirm_usd:
        return JSONResponse({"needs_confirmation": True, "estimate_usd": estimate}, status_code=409)

    booklet = Booklet(
        module_id=module_id,
        filename=file.filename or "booklet.pdf",
        pdf=data,
        page_count=page_count,
    )
    session.add(booklet)
    await session.flush()
    for index, piece in enumerate(slices):
        session.add(
            Chapter(
                booklet_id=booklet.id,
                index=index,
                title=piece.title,
                first_page=piece.first_page,
                last_page=piece.last_page,
                status=ChapterStatus.pending,
            )
        )
    await session.flush()
    return (await booklets_out(session, [booklet.id]))[booklet.id]


@router.get("/booklets/{booklet_id}/pdf")
async def booklet_pdf(booklet_id: int, session: Session) -> Response:
    booklet = await session.get(Booklet, booklet_id)
    if booklet is None:
        raise HTTPException(404, "Heft nicht gefunden")
    return Response(
        booklet.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.post("/chapters/{chapter_id}/retry")
async def retry_chapter(chapter_id: int, session: Session) -> ChapterOut:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404, "Kapitel nicht gefunden")
    if chapter.status != ChapterStatus.failed:
        raise HTTPException(409, "Nur fehlgeschlagene Kapitel koennen neu gestartet werden.")
    chapter.status = ChapterStatus.pending
    chapter.error = None
    chapter.batch_id = None
    chapter.draft = None
    chapter.waiting_reason = None
    chapter.waiting_since = None
    await session.flush()
    active = await session.scalar(
        select(func.count()).where(Item.chapter_id == chapter.id, Item.status == ItemStatus.active)
    )
    return chapter_out(chapter, active or 0)
