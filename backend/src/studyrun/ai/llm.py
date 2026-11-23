from __future__ import annotations

import base64
import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol, TypeVar, cast

import anthropic
from anthropic import AsyncAnthropic, transform_schema
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.ai.budget import ensure_budget
from studyrun.ai.ledger import record_call
from studyrun.ai.pricing import UnknownModel, Usage
from studyrun.config import Settings
from studyrun.models.db import Feature

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

_EFFORT = {Feature.generate: "high", Feature.verify: "medium", Feature.grade: "low"}
_MAX_TOKENS = {Feature.generate: 64_000, Feature.verify: 32_000, Feature.grade: 4_000}
# Two attempts of 10 s stay below the 30 s Kubernetes grace period, so a shutdown cannot
# cut off a submit whose batch id never reaches the database.
SUBMIT_TIMEOUT_SECONDS = 10.0
SUBMIT_MAX_RETRIES = 1

_TRANSIENT = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class LLMUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LLM(Protocol):
    async def structured(
        self,
        *,
        session: AsyncSession,
        feature: Feature,
        system: str,
        content: list[dict[str, Any]],
        schema: type[T],
        now: datetime,
    ) -> T: ...


class BatchLLM(Protocol):
    async def submit(
        self,
        *,
        session: AsyncSession,
        feature: Feature,
        custom_id: str,
        system: str,
        content: list[dict[str, Any]],
        schema: type[BaseModel],
        now: datetime,
    ) -> str: ...

    async def collect(
        self,
        *,
        session: AsyncSession,
        batch_id: str,
        feature: Feature,
        schema: type[T],
        now: datetime,
    ) -> T | None: ...


def pdf_block(data: bytes) -> dict[str, Any]:
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


def _usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=raw.input_tokens or 0,
        output_tokens=raw.output_tokens or 0,
        cache_read_tokens=raw.cache_read_input_tokens or 0,
        cache_write_tokens=raw.cache_creation_input_tokens or 0,
    )


def _final_text(blocks: Iterable[Any]) -> str:
    texts: list[str] = []
    for block in blocks:
        if block.type == "fallback":
            texts = []
        elif block.type == "text":
            texts.append(block.text)
    return "".join(texts)


def _parse[M: BaseModel](schema: type[M], message: Any) -> M:
    if message.stop_reason == "refusal":
        raise LLMUnavailable("Claude hat die Anfrage abgelehnt.")
    if message.stop_reason == "max_tokens":
        raise LLMUnavailable("Die Antwort von Claude wurde abgeschnitten.")
    try:
        return schema.model_validate_json(_final_text(message.content))
    except ValidationError:
        raise LLMUnavailable("Die Antwort von Claude hat nicht das erwartete Format.") from None


def _api_error(error: anthropic.AnthropicError) -> LLMUnavailable:
    return LLMUnavailable(f"Fehler der Claude-API: {error}")


class AnthropicLLM:
    def __init__(self, settings: Settings, *, client: AsyncAnthropic | None = None) -> None:
        self._settings = settings
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key or None)

    def _model(self, feature: Feature) -> str:
        return {
            Feature.generate: self._settings.model_generate,
            Feature.verify: self._settings.model_verify,
            Feature.grade: self._settings.model_grade,
        }[feature]

    def _params(
        self, feature: Feature, system: str, content: list[dict[str, Any]], schema: type[BaseModel]
    ) -> dict[str, Any]:
        return {
            "model": self._model(feature),
            "max_tokens": _MAX_TOKENS[feature],
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": _EFFORT[feature],
                "format": {"type": "json_schema", "schema": transform_schema(schema)},
            },
        }

    async def _record(
        self,
        session: AsyncSession,
        feature: Feature,
        model: str,
        usage: Usage,
        now: datetime,
        *,
        batch: bool,
    ) -> None:
        try:
            await record_call(session, feature, model, usage, now, batch=batch)
        except UnknownModel:
            requested = self._model(feature)
            log.warning("no price for %s, recording its usage at %s prices", model, requested)
            await record_call(session, feature, requested, usage, now, batch=batch)

    async def structured(
        self,
        *,
        session: AsyncSession,
        feature: Feature,
        system: str,
        content: list[dict[str, Any]],
        schema: type[T],
        now: datetime,
    ) -> T:
        await ensure_budget(session, feature, self._settings, now)
        params = self._params(feature, system, content, schema)
        try:
            message = await self._client.beta.messages.create(
                **params, fallbacks="default", betas=[FALLBACK_BETA]
            )
        except anthropic.AnthropicError as error:
            raise _api_error(error) from error

        attempts = [
            entry
            for entry in message.usage.iterations or []
            if entry.type in ("message", "fallback_message")
        ]
        if attempts:
            for entry in attempts:
                model = entry.model or params["model"]
                await self._record(session, feature, model, _usage(entry), now, batch=False)
        else:
            await self._record(
                session, feature, message.model, _usage(message.usage), now, batch=False
            )
        return _parse(schema, message)

    async def submit(
        self,
        *,
        session: AsyncSession,
        feature: Feature,
        custom_id: str,
        system: str,
        content: list[dict[str, Any]],
        schema: type[BaseModel],
        now: datetime,
    ) -> str:
        await ensure_budget(session, feature, self._settings, now)
        request = {"custom_id": custom_id, "params": self._params(feature, system, content, schema)}
        try:
            client = self._client.with_options(max_retries=SUBMIT_MAX_RETRIES)
            batch = await client.messages.batches.create(
                requests=[cast(Any, request)], timeout=SUBMIT_TIMEOUT_SECONDS
            )
        except anthropic.AnthropicError as error:
            raise _api_error(error) from error
        return batch.id

    async def collect(
        self,
        *,
        session: AsyncSession,
        batch_id: str,
        feature: Feature,
        schema: type[T],
        now: datetime,
    ) -> T | None:
        try:
            batch = await self._client.messages.batches.retrieve(batch_id)
            if batch.processing_status != "ended":
                return None
            results = [
                entry async for entry in await self._client.messages.batches.results(batch_id)
            ]
        except _TRANSIENT as error:
            log.warning("could not read batch %s, trying again later: %s", batch_id, error)
            return None
        except anthropic.AnthropicError as error:
            raise _api_error(error) from error

        if len(results) != 1:
            raise LLMUnavailable(f"Der Batch enthält {len(results)} Ergebnisse statt einem.")
        result = results[0].result
        if result.type == "errored":
            raise LLMUnavailable(f"Der Batch ist fehlgeschlagen: {result.error.error.message}")
        if result.type == "expired":
            raise LLMUnavailable("Der Batch ist abgelaufen.")
        if result.type == "canceled":
            raise LLMUnavailable("Der Batch wurde abgebrochen.")
        message = result.message
        await self._record(session, feature, message.model, _usage(message.usage), now, batch=True)
        return _parse(schema, message)
