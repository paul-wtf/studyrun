from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ChapterStatus(enum.StrEnum):
    pending = "pending"
    generating = "generating"
    verifying = "verifying"
    ready = "ready"
    failed = "failed"


class ItemKind(enum.StrEnum):
    mc = "mc"
    true_false = "true_false"
    cloze = "cloze"
    free = "free"


class ItemStatus(enum.StrEnum):
    active = "active"
    flagged = "flagged"
    deleted = "deleted"


class FlagReason(enum.StrEnum):
    wrong = "wrong"
    not_in_course = "not_in_course"
    unclear = "unclear"


class Feature(enum.StrEnum):
    generate = "generate"
    verify = "verify"
    grade = "grade"
    tutor = "tutor"


def _enum(cls: type[enum.StrEnum]) -> Enum:
    return Enum(
        cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Booklet(Base):
    __tablename__ = "booklets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("booklet_id", "index", name="uq_chapters_booklet_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booklet_id: Mapped[int] = mapped_column(
        ForeignKey("booklets.id", ondelete="CASCADE"), nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    first_page: Mapped[int] = mapped_column(Integer, nullable=False)
    last_page: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ChapterStatus] = mapped_column(
        _enum(ChapterStatus), nullable=False, default=ChapterStatus.pending
    )
    error: Mapped[str | None] = mapped_column(Text)
    waiting_reason: Mapped[str | None] = mapped_column(Text)
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    batch_id: Mapped[str | None] = mapped_column(String(255))
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    concepts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    introduced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[ItemKind] = mapped_column(_enum(ItemKind), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ItemStatus] = mapped_column(
        _enum(ItemStatus), nullable=False, default=ItemStatus.active
    )
    flag_reason: Mapped[FlagReason | None] = mapped_column(_enum(FlagReason))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (Index("ix_review_states_due", "due"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    card: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[int | None] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiCall(Base):
    __tablename__ = "api_calls"
    __table_args__ = (Index("ix_api_calls_at", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    feature: Mapped[Feature] = mapped_column(_enum(Feature), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
