from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from studyrun.models.db import Feature


@dataclass
class Call:
    feature: Feature
    system: str
    content: list[dict[str, Any]]
    schema: type[BaseModel]
    now: datetime
    custom_id: str | None = None
    batch_id: str | None = None


class FakeLLM:
    def __init__(self, responses: list[BaseModel | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[Call] = []

    async def structured(
        self,
        *,
        session: Any,
        feature: Feature,
        system: str,
        content: list[dict[str, Any]],
        schema: type[Any],
        now: datetime,
    ) -> Any:
        self.calls.append(Call(feature, system, content, schema, now))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, schema), f"queued {type(response)}, asked for {schema}"
        return response


Result = BaseModel | Exception | None


class FakeBatchLLM:
    """Results queued for a custom_id are handed out first; otherwise the shared queue
    is used, which also serves batch ids this fake never handed out (a restart)."""

    def __init__(
        self,
        results: list[Result] | None = None,
        *,
        submit_errors: list[Exception] | None = None,
    ) -> None:
        self.results = list(results or [])
        self.by_custom_id: dict[str, list[Result]] = {}
        self.submit_errors = list(submit_errors or [])
        self.submits: list[Call] = []
        self.collects: list[Call] = []
        self._custom_ids: dict[str, str] = {}

    def queue(self, custom_id: str, *results: Result) -> None:
        self.by_custom_id.setdefault(custom_id, []).extend(results)

    async def submit(
        self,
        *,
        session: Any,
        feature: Feature,
        custom_id: str,
        system: str,
        content: list[dict[str, Any]],
        schema: type[BaseModel],
        now: datetime,
    ) -> str:
        if self.submit_errors:
            raise self.submit_errors.pop(0)
        batch_id = f"msgbatch_fake_{len(self.submits) + 1}"
        self._custom_ids[batch_id] = custom_id
        self.submits.append(
            Call(feature, system, content, schema, now, custom_id=custom_id, batch_id=batch_id)
        )
        return batch_id

    async def collect(
        self,
        *,
        session: Any,
        batch_id: str,
        feature: Feature,
        schema: type[Any],
        now: datetime,
    ) -> Any:
        custom_id = self._custom_ids.get(batch_id)
        self.collects.append(Call(feature, "", [], schema, now, custom_id, batch_id))
        queued = self.by_custom_id.get(custom_id or "")
        if queued:
            result = queued.pop(0)
        elif self.results:
            result = self.results.pop(0)
        else:
            return None
        if isinstance(result, Exception):
            raise result
        if result is not None:
            assert isinstance(result, schema), f"queued {type(result)}, asked for {schema}"
        return result
