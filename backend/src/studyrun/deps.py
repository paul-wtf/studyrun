from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studyrun.ai.llm import LLM, AnthropicLLM
from studyrun.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session
        await session.commit()


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


def get_now() -> datetime:
    return datetime.now(UTC)


def get_llm(request: Request) -> LLM:
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        llm = request.app.state.llm = AnthropicLLM(get_settings())
    return llm
