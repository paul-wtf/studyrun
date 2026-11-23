from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.llm import BatchLLM, LLMUnavailable, pdf_block
from studyrun.content import prompts
from studyrun.content.pdf import extract_slice
from studyrun.content.schemas import ChapterContent, ItemUnion, McItem, Verification
from studyrun.content.validate import validate_items
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Feature, Item, ItemKind, ItemStatus

log = logging.getLogger(__name__)

WAITING_FOR_BUDGET = "Tagesbudget für die Erzeugung erreicht"
NO_VALID_ITEMS = "Keine gültigen Fragen erzeugt"
NO_ITEMS_PASSED = "Keine Fragen haben die Prüfung bestanden"
RETRYING_VERIFICATION = "Prüfung wird erneut versucht"
UNEXPECTED_ERROR = "Unerwarteter Fehler bei der Verarbeitung."

_ITEMS: TypeAdapter[list[ItemUnion]] = TypeAdapter(list[ItemUnion])


async def _chapter_pdf(session: AsyncSession, chapter: Chapter) -> dict[str, Any]:
    data = await session.scalar(select(Booklet.pdf).where(Booklet.id == chapter.booklet_id))
    if data is None:
        raise LookupError(f"booklet {chapter.booklet_id} is gone")
    return pdf_block(extract_slice(data, chapter.first_page, chapter.last_page))


def _wait(chapter: Chapter, now: datetime) -> None:
    chapter.waiting_reason = WAITING_FOR_BUDGET
    chapter.waiting_since = now


def _submitted(chapter: Chapter, status: ChapterStatus, batch_id: str) -> None:
    chapter.status = status
    chapter.batch_id = batch_id
    chapter.waiting_reason = None
    chapter.waiting_since = None
    chapter.error = None


def _fail(chapter: Chapter, message: str) -> None:
    chapter.status = ChapterStatus.failed
    chapter.error = message
    chapter.batch_id = None
    chapter.waiting_reason = None
    chapter.waiting_since = None


def verifiable(draft: dict[str, Any] | None) -> bool:
    if draft is None:
        return False
    try:
        return bool(ChapterContent.model_validate(draft).items)
    except ValidationError:
        return False


def _draft(chapter: Chapter) -> dict[str, Any]:
    if chapter.draft is None:
        raise LookupError(f"chapter {chapter.id} has no draft to verify")
    return chapter.draft


async def _submit_generation(
    session: AsyncSession, llm: BatchLLM, chapter: Chapter, now: datetime
) -> None:
    document = await _chapter_pdf(session, chapter)
    request = prompts.generation_request(chapter.title, chapter.first_page, chapter.last_page)
    try:
        batch_id = await llm.submit(
            session=session,
            feature=Feature.generate,
            custom_id=f"gen-{chapter.id}",
            system=prompts.GENERATION_SYSTEM,
            content=[document, {"type": "text", "text": request}],
            schema=ChapterContent,
            now=now,
        )
    except BudgetExceeded:
        _wait(chapter, now)
        return
    _submitted(chapter, ChapterStatus.generating, batch_id)


async def _submit_verification(
    session: AsyncSession, llm: BatchLLM, chapter: Chapter, now: datetime
) -> None:
    document = await _chapter_pdf(session, chapter)
    items = _ITEMS.validate_python(_draft(chapter)["items"])
    request = prompts.verification_request(chapter.first_page, chapter.last_page, items)
    try:
        batch_id = await llm.submit(
            session=session,
            feature=Feature.verify,
            custom_id=f"ver-{chapter.id}",
            system=prompts.VERIFICATION_SYSTEM,
            content=[document, {"type": "text", "text": request}],
            schema=Verification,
            now=now,
        )
    except BudgetExceeded:
        _wait(chapter, now)
        return
    except LLMUnavailable as error:
        log.warning("verification of chapter %s not submitted: %s", chapter.id, error.reason)
        if not error.retryable:
            _fail(chapter, error.reason)
            return
        chapter.batch_id = None
        chapter.waiting_reason = RETRYING_VERIFICATION
        chapter.waiting_since = None
        return
    _submitted(chapter, ChapterStatus.verifying, batch_id)


async def _collect_generation(
    session: AsyncSession, llm: BatchLLM, chapter: Chapter, now: datetime
) -> None:
    if chapter.batch_id is None:
        raise LookupError(f"chapter {chapter.id} is generating without a batch")
    generated = await llm.collect(
        session=session,
        batch_id=chapter.batch_id,
        feature=Feature.generate,
        schema=ChapterContent,
        now=now,
    )
    if generated is None:
        return
    if generated.no_content:
        chapter.status = ChapterStatus.skipped
        chapter.batch_id = None
        chapter.draft = None
        chapter.error = None
        return
    items = validate_items(generated.items, chapter.first_page, chapter.last_page)
    if not items:
        _fail(chapter, NO_VALID_ITEMS)
        return
    draft = ChapterContent(summary=generated.summary, concepts=generated.concepts, items=items)
    chapter.draft = draft.model_dump(mode="json")
    chapter.status = ChapterStatus.verifying
    chapter.batch_id = None
    await _submit_verification(session, llm, chapter, now)


def _passed(verification: Verification) -> set[int]:
    verdicts: dict[int, bool] = {}
    for verdict in verification.verdicts:
        ok = verdict.correct and verdict.in_source
        verdicts[verdict.index] = verdicts.get(verdict.index, True) and ok
    return {index for index, ok in verdicts.items() if ok}


def _stored_payload(item: ItemUnion, rng: random.Random) -> dict[str, Any]:
    payload = item.model_dump(mode="json", exclude={"kind", "source_page"})
    if isinstance(item, McItem):
        order = list(range(len(item.options)))
        rng.shuffle(order)
        payload["options"] = [item.options[i] for i in order]
        payload["answer_index"] = order.index(item.answer_index)
    return payload


async def _collect_verification(
    session: AsyncSession, llm: BatchLLM, chapter: Chapter, now: datetime, rng: random.Random
) -> None:
    if chapter.batch_id is None:
        await _submit_verification(session, llm, chapter, now)
        return
    verification = await llm.collect(
        session=session,
        batch_id=chapter.batch_id,
        feature=Feature.verify,
        schema=Verification,
        now=now,
    )
    if verification is None:
        return
    draft = _draft(chapter)
    passed = _passed(verification)
    items = [
        item
        for n, item in enumerate(_ITEMS.validate_python(draft["items"]), start=1)
        if n in passed
    ]
    if not items:
        _fail(chapter, NO_ITEMS_PASSED)
        chapter.draft = None
        return
    async with session.begin_nested():
        for item in items:
            session.add(
                Item(
                    chapter_id=chapter.id,
                    kind=ItemKind(item.kind),
                    payload=_stored_payload(item, rng),
                    source_page=item.source_page,
                    status=ItemStatus.active,
                )
            )
        chapter.summary = draft["summary"]
        chapter.concepts = draft["concepts"]
        chapter.draft = None
        chapter.batch_id = None
        chapter.error = None
        chapter.status = ChapterStatus.ready


_STEPS = {
    ChapterStatus.pending: _submit_generation,
    ChapterStatus.generating: _collect_generation,
}


async def advance_chapter(
    session: AsyncSession,
    llm: BatchLLM,
    chapter_id: int,
    now: datetime,
    *,
    rng: random.Random | None = None,
) -> None:
    chapter = await session.get(Chapter, chapter_id, with_for_update=True)
    if chapter is None or chapter.status not in (*_STEPS, ChapterStatus.verifying):
        return
    status = chapter.status
    try:
        if status == ChapterStatus.verifying:
            await _collect_verification(session, llm, chapter, now, rng or random.Random())
        else:
            await _STEPS[status](session, llm, chapter, now)
    except Exception as error:
        log.exception("chapter %s failed while %s", chapter_id, status.value)
        await session.refresh(chapter)
        _fail(chapter, error.reason if isinstance(error, LLMUnavailable) else UNEXPECTED_ERROR)
    await session.flush()
