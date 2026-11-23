from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select

from studyrun.content.schemas import ItemUnion
from studyrun.content.validate import validate_items
from studyrun.models.db import Chapter, FlagReason, Item, ItemKind, ItemStatus
from studyrun.routes.modules import Session
from studyrun.routes.runs import pdf_link

router = APIRouter()

_ITEM: TypeAdapter[ItemUnion] = TypeAdapter(ItemUnion)


class FlagIn(BaseModel):
    reason: FlagReason


class FlaggedOut(BaseModel):
    status: Literal["flagged"]


@router.post("/items/{item_id}/flag")
async def flag_item(item_id: int, body: FlagIn, session: Session) -> FlaggedOut:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    item.status = ItemStatus.flagged
    item.flag_reason = body.reason
    await session.flush()
    return FlaggedOut(status="flagged")


class ItemFix(BaseModel):
    payload: dict[str, Any]
    source_page: int | None = None


class FlagOut(BaseModel):
    id: int
    kind: ItemKind
    payload: dict[str, Any]
    source_page: int
    reason: FlagReason | None
    chapter_title: str
    source: str


@router.get("/flags")
async def list_flags(session: Session) -> list[FlagOut]:
    rows = await session.execute(
        select(Item, Chapter)
        .join(Chapter, Chapter.id == Item.chapter_id)
        .where(Item.status == ItemStatus.flagged)
        .order_by(Item.id)
    )
    return [
        FlagOut(
            id=item.id,
            kind=item.kind,
            payload=item.payload,
            source_page=item.source_page,
            reason=item.flag_reason,
            chapter_title=chapter.title,
            source=pdf_link(chapter.booklet_id, item.source_page),
        )
        for item, chapter in rows.all()
    ]


@router.put("/items/{item_id}")
async def fix_item(item_id: int, body: ItemFix, session: Session) -> dict[str, str]:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    if item.status != ItemStatus.flagged:
        raise HTTPException(409, "Nur gemeldete Fragen können bearbeitet werden.")
    chapter = await session.get(Chapter, item.chapter_id)
    assert chapter is not None
    page = body.source_page if body.source_page is not None else item.source_page
    fields = {
        key: value for key, value in body.payload.items() if key not in ("kind", "source_page")
    }
    try:
        parsed = _ITEM.validate_python({**fields, "kind": item.kind.value, "source_page": page})
    except ValidationError as exc:
        raise HTTPException(422, "Ungültige Aufgabe: " + str(exc.errors()[0]["msg"])) from exc
    if not validate_items([parsed], chapter.first_page, chapter.last_page):
        raise HTTPException(422, "Ungültige Aufgabe: Inhalt oder Quellseite passt nicht.")
    item.payload = parsed.model_dump(exclude={"kind", "source_page"})
    item.source_page = page
    item.status = ItemStatus.active
    item.flag_reason = None
    await session.flush()
    return {"status": item.status.value}


@router.delete("/items/{item_id}")
async def delete_item(item_id: int, session: Session) -> dict[str, str]:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    if item.status != ItemStatus.flagged:
        raise HTTPException(409, "Nur gemeldete Fragen können gelöscht werden.")
    item.status = ItemStatus.deleted
    await session.flush()
    return {"status": item.status.value}
