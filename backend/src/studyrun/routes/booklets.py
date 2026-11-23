from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.config import Settings
from studyrun.content.pdf import BookletError, split_booklet
from studyrun.content.pipeline import verifiable
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


def _matches(if_none_match: str | None, etag: str) -> bool:
    if if_none_match is None:
        return False
    tags = [tag.strip().removeprefix("W/") for tag in if_none_match.split(",")]
    return "*" in tags or etag in tags


@router.get("/booklets/{booklet_id}/pdf")
async def booklet_pdf(
    booklet_id: int,
    session: Session,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    created_at = await session.scalar(select(Booklet.created_at).where(Booklet.id == booklet_id))
    if created_at is None:
        raise HTTPException(404, "Heft nicht gefunden")
    etag = f'"{booklet_id}-{created_at.timestamp():.6f}"'
    headers = {"Cache-Control": "private, max-age=86400", "ETag": etag}
    if _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    data = await session.scalar(select(Booklet.pdf).where(Booklet.id == booklet_id))
    return Response(
        data,
        media_type="application/pdf",
        headers={**headers, "Content-Disposition": "inline"},
    )


async def _get_chapter(session: AsyncSession, chapter_id: int) -> Chapter:
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(404, "Kapitel nicht gefunden")
    return chapter


async def _chapter_out(session: AsyncSession, chapter: Chapter) -> ChapterOut:
    await session.flush()
    active = await session.scalar(
        select(func.count()).where(Item.chapter_id == chapter.id, Item.status == ItemStatus.active)
    )
    return chapter_out(chapter, active or 0)


@router.post("/chapters/{chapter_id}/retry")
async def retry_chapter(chapter_id: int, session: Session) -> ChapterOut:
    chapter = await _get_chapter(session, chapter_id)
    if chapter.status != ChapterStatus.failed:
        raise HTTPException(409, "Nur fehlgeschlagene Kapitel können neu gestartet werden.")
    if verifiable(chapter.draft):
        chapter.status = ChapterStatus.verifying
    else:
        chapter.status = ChapterStatus.pending
        chapter.draft = None
    chapter.error = None
    chapter.batch_id = None
    chapter.waiting_reason = None
    chapter.waiting_since = None
    return await _chapter_out(session, chapter)


@router.post("/chapters/{chapter_id}/skip")
async def skip_chapter(chapter_id: int, session: Session) -> ChapterOut:
    chapter = await _get_chapter(session, chapter_id)
    if chapter.status not in (ChapterStatus.failed, ChapterStatus.pending):
        raise HTTPException(
            409, "Nur fehlgeschlagene oder wartende Kapitel können übersprungen werden."
        )
    chapter.status = ChapterStatus.skipped
    chapter.error = None
    chapter.batch_id = None
    chapter.draft = None
    chapter.waiting_reason = None
    chapter.waiting_since = None
    return await _chapter_out(session, chapter)
