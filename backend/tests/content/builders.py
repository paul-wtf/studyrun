from __future__ import annotations

from datetime import datetime
from typing import Any

from pdfs import build_pdf
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.content.schemas import (
    ChapterContent,
    ClozeItem,
    Concept,
    FreeItem,
    McItem,
    TrueFalseItem,
    Verdict,
    Verification,
)
from studyrun.models.db import Booklet, Chapter, ChapterStatus, Module


def mc(page: int = 2, **overrides: Any) -> McItem:
    values: dict[str, Any] = {
        "kind": "mc",
        "prompt": "Welche Farbe hat der erfundene Testvogel?",
        "options": ["Blau", "Grün", "Rot"],
        "answer_index": 1,
        "explanation": "Im Beispieltext ist der Vogel grün.",
        "source_page": page,
    }
    return McItem(**(values | overrides))


def true_false(page: int = 2, **overrides: Any) -> TrueFalseItem:
    values: dict[str, Any] = {
        "kind": "true_false",
        "statement": "Der Testvogel kann schwimmen.",
        "correct": False,
        "explanation": "Der Beispieltext sagt, er meidet Wasser.",
        "source_page": page,
    }
    return TrueFalseItem(**(values | overrides))


def cloze(page: int = 2, **overrides: Any) -> ClozeItem:
    values: dict[str, Any] = {
        "kind": "cloze",
        "text": "Der Testvogel frisst am liebsten ___.",
        "answers": ["Körner"],
        "explanation": "So steht es im Beispieltext.",
        "source_page": page,
    }
    return ClozeItem(**(values | overrides))


def free(page: int = 2, **overrides: Any) -> FreeItem:
    values: dict[str, Any] = {
        "kind": "free",
        "prompt": "Warum meidet der Testvogel Wasser?",
        "model_answer": "Sein Gefieder ist nicht wasserabweisend.",
        "rubric": ["nennt das Gefieder", "nennt fehlende Wasserabweisung"],
        "source_excerpt": "Das Gefieder des Testvogels ist nicht wasserabweisend.",
        "source_page": page,
    }
    return FreeItem(**(values | overrides))


def content(items: list[Any]) -> ChapterContent:
    return ChapterContent(
        summary="Ein erfundenes Kapitel über den Testvogel.",
        concepts=[Concept(term="Testvogel", explanation="Ein erfundener Vogel.")],
        items=items,
    )


def verdicts(*passing: bool, start: int = 1) -> Verification:
    return Verification(
        verdicts=[
            Verdict(index=n, correct=ok, in_source=True, note="")
            for n, ok in enumerate(passing, start=start)
        ]
    )


async def seed_module(session: AsyncSession, *, position: int = 1, name: str = "M1") -> Module:
    module = Module(name=name, position=position)
    session.add(module)
    await session.flush()
    return module


async def seed_booklet(session: AsyncSession, module: Module, *, pages: int = 6) -> Booklet:
    booklet = Booklet(
        module_id=module.id, filename="heft.pdf", pdf=build_pdf(pages), page_count=pages
    )
    session.add(booklet)
    await session.flush()
    return booklet


async def seed_chapter(
    session: AsyncSession,
    booklet: Booklet,
    *,
    index: int = 0,
    first_page: int = 2,
    last_page: int = 5,
    status: ChapterStatus = ChapterStatus.pending,
    batch_id: str | None = None,
    draft: dict[str, Any] | None = None,
    waiting_reason: str | None = None,
    waiting_since: datetime | None = None,
) -> Chapter:
    chapter = Chapter(
        booklet_id=booklet.id,
        index=index,
        title=f"Kapitel {index + 1}",
        first_page=first_page,
        last_page=last_page,
        status=status,
        batch_id=batch_id,
        draft=draft,
        waiting_reason=waiting_reason,
        waiting_since=waiting_since,
    )
    session.add(chapter)
    await session.flush()
    return chapter


async def seed_pending(session: AsyncSession, **chapter: Any) -> Chapter:
    module = await seed_module(session)
    booklet = await seed_booklet(session, module)
    return await seed_chapter(session, booklet, **chapter)
