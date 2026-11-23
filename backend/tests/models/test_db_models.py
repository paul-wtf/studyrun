from datetime import UTC, datetime

from sqlalchemy import delete, func, select

from studyrun.models.db import (
    Booklet,
    Chapter,
    ChapterStatus,
    Item,
    ItemKind,
    ItemStatus,
    Module,
    ReviewLog,
    ReviewState,
)


async def _chapter_with_item(session, payload=None):
    module = Module(name="Biologie", position=0)
    session.add(module)
    await session.flush()
    booklet = Booklet(module_id=module.id, filename="heft.pdf", pdf=b"%PDF", page_count=10)
    session.add(booklet)
    await session.flush()
    chapter = Chapter(
        booklet_id=booklet.id,
        index=0,
        title="Zellen",
        first_page=1,
        last_page=10,
        status=ChapterStatus.ready,
    )
    session.add(chapter)
    await session.flush()
    item = Item(
        chapter_id=chapter.id,
        kind=ItemKind.free,
        payload=payload or {"question": "Was ist eine Zelle?"},
        source_page=3,
        status=ItemStatus.active,
    )
    session.add(item)
    await session.flush()
    session.add(ReviewState(item_id=item.id, card={"state": 1}, due=datetime.now(UTC)))
    session.add(ReviewLog(item_id=item.id, rating=3))
    await session.flush()
    return booklet, chapter, item


async def test_chapter_cascade(db_session):
    booklet, _, _ = await _chapter_with_item(db_session)

    await db_session.execute(delete(Booklet).where(Booklet.id == booklet.id))

    for model in (Chapter, Item, ReviewState, ReviewLog):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0


async def test_item_payload_roundtrip(db_session):
    payload = {"question": "Wofür steht die Mitochondrie?", "antwort": "Energie — Größe äöüß"}
    _, _, item = await _chapter_with_item(db_session, payload)
    item_id = item.id
    db_session.expire_all()

    stored = await db_session.get(Item, item_id)

    assert stored is not None
    assert stored.payload == payload
    assert stored.kind is ItemKind.free
