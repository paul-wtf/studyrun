from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from studyrun.models.db import FlagReason, Item, ItemStatus
from studyrun.routes.modules import Session

router = APIRouter()


class FlagIn(BaseModel):
    reason: FlagReason


@router.post("/items/{item_id}/flag")
async def flag_item(item_id: int, body: FlagIn, session: Session) -> dict[str, str]:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    item.status = ItemStatus.flagged
    item.flag_reason = body.reason
    await session.flush()
    return {"status": item.status.value}
