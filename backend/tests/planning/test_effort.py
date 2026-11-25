from datetime import UTC, datetime

from fsrs import Card, State

from studyrun.models.db import (
    Booklet,
    Chapter,
    ChapterStatus,
    Item,
    ItemKind,
    ItemStatus,
    Module,
    ReviewState,
    Subject,
)
from studyrun.planning.effort import subject_effort

NOW = datetime(2026, 11, 24, 9, tzinfo=UTC)


async def make_subject(session, name="Fach"):
    subject = Subject(name=name, duration_minutes=90, earliest_semester="3a", sittings=[])
    session.add(subject)
    await session.flush()
    return subject


async def make_booklet(session, subject):
    module = Module(name="Modul", position=0, subject_id=subject.id if subject else None)
    session.add(module)
    await session.flush()
    booklet = Booklet(module_id=module.id, filename="b.pdf", pdf=b"", page_count=40)
    session.add(booklet)
    await session.flush()
    return booklet


async def make_chapter(session, booklet, index, status, pages=(1, 10)):
    chapter = Chapter(
        booklet_id=booklet.id,
        index=index,
        title=f"Kapitel {index}",
        first_page=pages[0],
        last_page=pages[1],
        status=status,
    )
    session.add(chapter)
    await session.flush()
    return chapter


async def make_item(session, chapter, state=None, status=ItemStatus.active):
    item = Item(chapter_id=chapter.id, kind=ItemKind.mc, payload={}, source_page=1, status=status)
    session.add(item)
    await session.flush()
    if state is not None:
        card = Card(state=state, step=None if state == State.Review else 0, due=NOW)
        session.add(ReviewState(item_id=item.id, card=card.to_dict(), due=NOW))
        await session.flush()
    return item


async def test_counts_unseen_and_learning_items(db_session):
    subject = await make_subject(db_session)
    booklet = await make_booklet(db_session, subject)
    ready = await make_chapter(db_session, booklet, 0, ChapterStatus.ready)
    for state in (None, None, State.Learning, State.Relearning, State.Review):
        await make_item(db_session, ready, state)
    await make_item(db_session, ready, None, ItemStatus.deleted)
    await make_item(db_session, ready, None, ItemStatus.flagged)

    assert await subject_effort(db_session, subject.id) == (4, True)


async def test_unready_chapters_estimate_two_items_per_page(db_session):
    subject = await make_subject(db_session)
    booklet = await make_booklet(db_session, subject)
    await make_chapter(db_session, booklet, 0, ChapterStatus.pending, (1, 5))
    await make_chapter(db_session, booklet, 1, ChapterStatus.generating, (6, 6))
    await make_chapter(db_session, booklet, 2, ChapterStatus.verifying, (7, 8))
    await make_chapter(db_session, booklet, 3, ChapterStatus.failed, (9, 11))
    await make_chapter(db_session, booklet, 4, ChapterStatus.skipped, (12, 40))

    assert await subject_effort(db_session, subject.id) == (2 * (5 + 1 + 2 + 3), True)


async def test_skipped_chapters_and_other_subjects_are_excluded(db_session):
    subject = await make_subject(db_session)
    other = await make_subject(db_session, "Anderes Fach")
    booklet = await make_booklet(db_session, subject)
    skipped = await make_chapter(db_session, booklet, 0, ChapterStatus.skipped)
    await make_item(db_session, skipped)
    ready = await make_chapter(db_session, booklet, 1, ChapterStatus.ready)
    await make_item(db_session, ready)
    foreign = await make_chapter(
        db_session, await make_booklet(db_session, other), 0, ChapterStatus.ready
    )
    await make_item(db_session, foreign)
    await make_chapter(db_session, await make_booklet(db_session, None), 0, ChapterStatus.pending)

    assert await subject_effort(db_session, subject.id) == (1, True)


async def test_learned_material_has_no_effort_but_counts_as_material(db_session):
    subject = await make_subject(db_session)
    booklet = await make_booklet(db_session, subject)
    ready = await make_chapter(db_session, booklet, 0, ChapterStatus.ready)
    await make_item(db_session, ready, State.Review)

    assert await subject_effort(db_session, subject.id) == (0, True)


async def test_no_booklet_means_no_material(db_session):
    subject = await make_subject(db_session)
    assert await subject_effort(db_session, subject.id) == (0, False)
    db_session.add(Module(name="Leer", position=0, subject_id=subject.id))
    await db_session.flush()
    assert await subject_effort(db_session, subject.id) == (0, False)
