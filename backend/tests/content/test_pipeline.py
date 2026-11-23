import base64
import io
from datetime import datetime
from decimal import Decimal

from builders import content, free, mc, seed_pending, true_false, verdicts
from fakes import FakeBatchLLM
from pypdf import PdfReader
from sqlalchemy import func, select

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.llm import LLMUnavailable
from studyrun.content import prompts
from studyrun.content.pipeline import advance_chapter
from studyrun.content.schemas import ChapterContent, Verification
from studyrun.models.db import Chapter, ChapterStatus, Feature, Item, ItemStatus, ReviewState

NOW = datetime.fromisoformat("2026-11-23T12:00:00+01:00")


def _budget() -> BudgetExceeded:
    return BudgetExceeded(Feature.generate, Decimal(10), Decimal(10))


async def _reload(session, chapter_id: int) -> Chapter:
    chapter = await session.get(Chapter, chapter_id, populate_existing=True)
    assert chapter is not None
    return chapter


async def _advance(session, llm, chapter_id: int) -> Chapter:
    await advance_chapter(session, llm, chapter_id, NOW)
    return await _reload(session, chapter_id)


async def test_ready_with_verified_items(db_session):
    chapter = await seed_pending(db_session, first_page=2, last_page=5)
    generated = [
        mc(page=2),
        true_false(page=3),
        mc(page=9, prompt="Diese Frage liegt außerhalb des Kapitels."),
        free(page=4),
        mc(page=5, prompt="Wie heißt der erfundene Testfluss?"),
    ]
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content(generated))
    llm.queue(f"ver-{chapter.id}", verdicts(True, False, True, True))

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.generating
    assert chapter.batch_id == llm.submits[0].batch_id
    gen = llm.submits[0]
    assert (gen.custom_id, gen.feature, gen.schema) == (
        f"gen-{chapter.id}",
        Feature.generate,
        ChapterContent,
    )
    document = gen.content[0]
    assert document["type"] == "document"
    assert document["source"]["media_type"] == "application/pdf"
    pdf = PdfReader(io.BytesIO(base64.b64decode(document["source"]["data"])))
    assert len(pdf.pages) == 4
    assert gen.content[1]["type"] == "text"

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.verifying
    ver = llm.submits[1]
    assert (ver.custom_id, ver.feature, ver.schema) == (
        f"ver-{chapter.id}",
        Feature.verify,
        Verification,
    )
    assert chapter.batch_id == ver.batch_id
    assert ver.content[0] == document
    request = ver.content[1]["text"]
    for n in range(1, 5):
        assert f'"index": {n}' in request
    assert '"index": 5' not in request
    assert "außerhalb des Kapitels" not in request
    assert chapter.draft is not None and len(chapter.draft["items"]) == 4

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.ready
    assert chapter.summary == "Ein erfundenes Kapitel über den Testvogel."
    assert chapter.concepts == [{"term": "Testvogel", "explanation": "Ein erfundener Vogel."}]
    assert chapter.draft is None
    assert chapter.batch_id is None
    assert chapter.error is None
    items = (
        (
            await db_session.execute(
                select(Item).where(Item.chapter_id == chapter.id).order_by(Item.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(i.kind.value, i.source_page, i.status) for i in items] == [
        ("mc", 2, ItemStatus.active),
        ("free", 4, ItemStatus.active),
        ("mc", 5, ItemStatus.active),
    ]
    assert items[2].payload["prompt"] == "Wie heißt der erfundene Testfluss?"
    assert items[1].payload["rubric"] == ["nennt das Gefieder", "nennt fehlende Wasserabweisung"]
    assert await db_session.scalar(select(func.count()).select_from(ReviewState)) == 0


async def test_chapter_without_learnable_content_is_skipped(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(
        f"gen-{chapter.id}",
        ChapterContent(no_content=True, summary="", concepts=[], items=[]),
    )
    await _advance(db_session, llm, chapter.id)
    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.skipped
    assert (chapter.batch_id, chapter.draft, chapter.error) == (None, None, None)
    assert [c.feature for c in llm.submits] == [Feature.generate]
    assert await db_session.scalar(select(func.count()).select_from(Item)) == 0


def test_generation_asks_about_learnable_content():
    assert "no_content" in ChapterContent.model_json_schema()["properties"]
    assert "no_content" in prompts.GENERATION_SYSTEM
    assert "Inhaltsverzeichnis" in prompts.GENERATION_SYSTEM


async def test_stays_while_batch_processing(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", None, content([mc()]))
    llm.queue(f"ver-{chapter.id}", None, verdicts(True))

    chapter = await _advance(db_session, llm, chapter.id)
    batch_id = chapter.batch_id
    chapter = await _advance(db_session, llm, chapter.id)
    assert (chapter.status, chapter.batch_id) == (ChapterStatus.generating, batch_id)

    chapter = await _advance(db_session, llm, chapter.id)
    batch_id = chapter.batch_id
    chapter = await _advance(db_session, llm, chapter.id)
    assert (chapter.status, chapter.batch_id) == (ChapterStatus.verifying, batch_id)
    assert chapter.draft is not None

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.ready
    assert len(llm.submits) == 2


async def test_missing_verdict_rejects(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc(), true_false(), free()]))
    llm.queue(f"ver-{chapter.id}", verdicts(True, True))
    for _ in range(3):
        chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.ready
    kinds = (
        await db_session.execute(select(Item.kind).where(Item.chapter_id == chapter.id))
    ).scalars()
    assert sorted(k.value for k in kinds) == ["mc", "true_false"]


async def test_verdict_must_be_correct_and_in_source(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc(), true_false()]))
    result = verdicts(True, True)
    result.verdicts[1].in_source = False
    llm.queue(f"ver-{chapter.id}", result)
    for _ in range(3):
        chapter = await _advance(db_session, llm, chapter.id)
    count = await db_session.scalar(
        select(func.count()).select_from(Item).where(Item.chapter_id == chapter.id)
    )
    assert (chapter.status, count) == (ChapterStatus.ready, 1)


async def test_all_invalid_fails(db_session):
    chapter = await seed_pending(db_session, first_page=2, last_page=5)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc(page=1), mc(answer_index=7)]))
    await _advance(db_session, llm, chapter.id)
    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.failed
    assert chapter.error == "Keine gültigen Fragen erzeugt"
    assert chapter.batch_id is None
    assert len(llm.submits) == 1


async def test_all_rejected_fails(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc(), free()]))
    llm.queue(f"ver-{chapter.id}", verdicts(False, False))
    for _ in range(3):
        chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.failed
    assert chapter.error == "Keine Fragen haben die Prüfung bestanden"
    assert chapter.batch_id is None
    assert chapter.draft is None
    count = await db_session.scalar(select(func.count()).select_from(Item))
    assert count == 0


async def test_budget_exceeded_waits(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM(submit_errors=[_budget()])
    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.pending
    assert chapter.waiting_reason == "Tagesbudget für die Erzeugung erreicht"
    assert chapter.waiting_since == NOW
    assert chapter.batch_id is None
    assert chapter.error is None

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.generating
    assert chapter.waiting_reason is None
    assert chapter.waiting_since is None


async def test_verification_waits_for_budget(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc()]))
    llm.queue(f"ver-{chapter.id}", verdicts(True))
    await _advance(db_session, llm, chapter.id)
    llm.submit_errors.append(_budget())

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.verifying
    assert chapter.batch_id is None
    assert chapter.draft is not None
    assert chapter.waiting_reason == "Tagesbudget für die Erzeugung erreicht"

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.verifying
    assert chapter.batch_id == llm.submits[1].batch_id
    assert chapter.waiting_reason is None

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.ready


async def test_verification_submit_error_keeps_the_draft(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc(), true_false()]))
    llm.queue(f"ver-{chapter.id}", verdicts(True, True))
    await _advance(db_session, llm, chapter.id)
    llm.submit_errors += [
        LLMUnavailable("Fehler der Claude-API: overloaded"),
        LLMUnavailable("Fehler der Claude-API: overloaded"),
    ]

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.verifying
    assert chapter.batch_id is None
    assert chapter.draft is not None and len(chapter.draft["items"]) == 2
    assert chapter.waiting_reason == "Prüfung wird erneut versucht"
    assert chapter.waiting_since is None
    assert chapter.error is None

    chapter = await _advance(db_session, llm, chapter.id)
    assert (chapter.status, chapter.batch_id) == (ChapterStatus.verifying, None)

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.batch_id == llm.submits[-1].batch_id
    assert chapter.waiting_reason is None

    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.ready
    assert [c.feature for c in llm.submits] == [Feature.generate, Feature.verify]


async def test_batch_error_fails_with_message(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", LLMUnavailable("Der Batch ist abgelaufen."))
    await _advance(db_session, llm, chapter.id)
    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.failed
    assert chapter.error == "Der Batch ist abgelaufen."
    assert chapter.batch_id is None


async def test_unexpected_error_fails_with_message(db_session):
    chapter = await seed_pending(db_session)
    llm = FakeBatchLLM()
    llm.queue(f"gen-{chapter.id}", content([mc()]))
    llm.queue(f"ver-{chapter.id}", RuntimeError("Verbindung verloren"))
    for _ in range(3):
        chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.failed
    assert chapter.error == "Verbindung verloren"
    assert chapter.batch_id is None


async def test_finished_chapters_are_left_alone(db_session):
    chapter = await seed_pending(db_session, status=ChapterStatus.ready)
    llm = FakeBatchLLM()
    chapter = await _advance(db_session, llm, chapter.id)
    assert chapter.status == ChapterStatus.ready
    assert llm.submits == [] and llm.collects == []
