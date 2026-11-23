import json
from datetime import datetime
from decimal import Decimal

import httpx2
import pytest
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient
from pydantic import BaseModel
from sqlalchemy import select

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.ledger import record_call
from studyrun.ai.llm import AnthropicLLM, LLMUnavailable, pdf_block
from studyrun.ai.pricing import Usage
from studyrun.config import Settings
from studyrun.models.db import ApiCall, Feature

NOW = datetime.fromisoformat("2026-11-23T12:00:00+01:00")
CONTENT = [pdf_block(b"%PDF-1.7 fake"), {"type": "text", "text": "Bewerte die Antwort."}]
USAGE = {
    "input_tokens": 1000,
    "output_tokens": 200,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
}


class Grade(BaseModel):
    score: int
    feedback: str


def _message(text: str, *, stop_reason: str = "end_turn", **extra) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": USAGE,
        **extra,
    }


def _batch(status: str) -> dict:
    return {
        "id": "msgbatch_1",
        "type": "message_batch",
        "processing_status": status,
        "request_counts": {
            "processing": 0 if status == "ended" else 1,
            "succeeded": 0,
            "errored": 0,
            "canceled": 0,
            "expired": 0,
        },
        "created_at": "2026-11-23T10:00:00Z",
        "expires_at": "2026-11-24T10:00:00Z",
        "ended_at": "2026-11-23T10:30:00Z" if status == "ended" else None,
        "results_url": (
            "https://api.anthropic.com/v1/messages/batches/msgbatch_1/results"
            if status == "ended"
            else None
        ),
    }


class Api:
    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def body(self, n: int = 0) -> dict:
        return json.loads(self.requests[n].content)


def _llm(api: Api) -> AnthropicLLM:
    client = AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(api)),
    )
    return AnthropicLLM(Settings(anthropic_api_key="test-key"), client=client)


async def _calls(session) -> list[ApiCall]:
    return list((await session.execute(select(ApiCall).order_by(ApiCall.id))).scalars())


async def test_structured_request_and_cost(db_session):
    api = Api(httpx2.Response(200, json=_message('{"score": 2, "feedback": "Gut."}')))
    grade = await _llm(api).structured(
        session=db_session,
        feature=Feature.grade,
        system="Du bewertest Antworten.",
        content=CONTENT,
        schema=Grade,
        now=NOW,
    )
    assert grade == Grade(score=2, feedback="Gut.")

    request = api.requests[0]
    assert request.url.path == "/v1/messages"
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    body = api.body()
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["system"] == [
        {"type": "text", "text": "Du bewertest Antworten.", "cache_control": {"type": "ephemeral"}}
    ]
    assert body["messages"] == [{"role": "user", "content": CONTENT}]
    assert body["thinking"] == {"type": "adaptive"}
    assert body["max_tokens"] == 4000
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert set(body["output_config"]["format"]["schema"]["properties"]) == {"score", "feedback"}

    [call] = await _calls(db_session)
    assert (call.feature, call.model, call.batch) == (Feature.grade, "claude-opus-5-5", False)
    assert call.cost_usd == Decimal("0.008000")


async def test_structured_refusal_is_unavailable_and_still_billed(db_session):
    api = Api(httpx2.Response(200, json=_message("", stop_reason="refusal")))
    with pytest.raises(LLMUnavailable):
        await _llm(api).structured(
            session=db_session,
            feature=Feature.grade,
            system="s",
            content=CONTENT,
            schema=Grade,
            now=NOW,
        )
    assert len(await _calls(db_session)) == 1


async def test_structured_records_each_fallback_attempt(db_session):
    usage = {
        **USAGE,
        "iterations": [
            {**USAGE, "type": "message", "model": "claude-opus-5-5", "output_tokens": 0},
            {**USAGE, "type": "fallback_message", "model": "claude-opus-5"},
        ],
    }
    message = _message('{"score": 1, "feedback": "Teilweise."}', model="claude-opus-5")
    message["usage"] = usage
    api = Api(httpx2.Response(200, json=message))
    await _llm(api).structured(
        session=db_session,
        feature=Feature.grade,
        system="s",
        content=CONTENT,
        schema=Grade,
        now=NOW,
    )
    calls = await _calls(db_session)
    assert [(c.model, c.cost_usd) for c in calls] == [
        ("claude-opus-5-5", Decimal("0.004000")),
        ("claude-opus-5", Decimal("0.010000")),
    ]


async def test_structured_api_error_is_unavailable(db_session, caplog):
    api = Api(
        httpx2.Response(
            400,
            json={"type": "error", "error": {"type": "invalid_request_error", "message": "kaputt"}},
        )
    )
    with pytest.raises(LLMUnavailable) as raised:
        await _llm(api).structured(
            session=db_session,
            feature=Feature.grade,
            system="s",
            content=CONTENT,
            schema=Grade,
            now=NOW,
        )
    assert raised.value.reason == "Die Claude-API hat mit Fehler 400 geantwortet."
    assert "kaputt" in caplog.text


async def test_structured_invalid_json_is_unavailable(db_session):
    api = Api(httpx2.Response(200, json=_message('{"score": "viel"}')))
    with pytest.raises(LLMUnavailable):
        await _llm(api).structured(
            session=db_session,
            feature=Feature.grade,
            system="s",
            content=CONTENT,
            schema=Grade,
            now=NOW,
        )
    assert len(await _calls(db_session)) == 1


async def test_structured_checks_budget_first(db_session):
    await record_call(db_session, Feature.grade, "claude-opus-5-5", Usage(125_000, 0, 0, 0), NOW)
    api = Api()
    with pytest.raises(BudgetExceeded):
        await _llm(api).structured(
            session=db_session,
            feature=Feature.grade,
            system="s",
            content=CONTENT,
            schema=Grade,
            now=NOW,
        )
    assert api.requests == []


async def test_submit_creates_one_request_batch(db_session):
    api = Api(httpx2.Response(200, json=_batch("in_progress")))
    batch_id = await _llm(api).submit(
        session=db_session,
        feature=Feature.verify,
        custom_id="ver-7",
        system="Du prüfst Fragen.",
        content=CONTENT,
        schema=Grade,
        now=NOW,
    )
    assert batch_id == "msgbatch_1"
    assert api.requests[0].url.path == "/v1/messages/batches"
    assert api.requests[0].extensions["timeout"]["read"] <= 25
    [request] = api.body()["requests"]
    assert request["custom_id"] == "ver-7"
    params = request["params"]
    assert params["model"] == "claude-sonnet-5-5"
    assert "fallbacks" not in params
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["messages"] == [{"role": "user", "content": CONTENT}]
    assert params["output_config"]["effort"] == "medium"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert await _calls(db_session) == []


async def test_submit_retries_once_within_the_shutdown_window(db_session):
    overloaded = httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error"}})
    api = Api(overloaded, overloaded, httpx2.Response(200, json=_batch("in_progress")))
    with pytest.raises(LLMUnavailable):
        await _llm(api).submit(
            session=db_session,
            feature=Feature.generate,
            custom_id="gen-7",
            system="Du erzeugst Fragen.",
            content=CONTENT,
            schema=Grade,
            now=NOW,
        )
    assert len(api.requests) == 2
    assert all(r.extensions["timeout"]["read"] == 10 for r in api.requests)


async def test_submit_checks_budget_first(db_session):
    await record_call(
        db_session, Feature.generate, "claude-opus-5-5", Usage(2_500_000, 0, 0, 0), NOW
    )
    api = Api()
    with pytest.raises(BudgetExceeded):
        await _llm(api).submit(
            session=db_session,
            feature=Feature.generate,
            custom_id="gen-1",
            system="s",
            content=CONTENT,
            schema=Grade,
            now=NOW,
        )
    assert api.requests == []


async def _collect(db_session, api: Api):
    return await _llm(api).collect(
        session=db_session, batch_id="msgbatch_1", feature=Feature.verify, schema=Grade, now=NOW
    )


def _results(result: dict) -> httpx2.Response:
    line = json.dumps({"custom_id": "ver-7", "result": result})
    return httpx2.Response(200, content=line.encode() + b"\n")


async def test_collect_while_processing(db_session):
    api = Api(httpx2.Response(200, json=_batch("in_progress")))
    assert await _collect(db_session, api) is None
    assert await _calls(db_session) == []


async def test_collect_success_records_batch_cost(db_session):
    message = _message('{"score": 0, "feedback": "Falsch."}', model="claude-sonnet-5-5")
    api = Api(
        httpx2.Response(200, json=_batch("ended")),
        httpx2.Response(200, json=_batch("ended")),
        _results({"type": "succeeded", "message": message}),
    )
    assert await _collect(db_session, api) == Grade(score=0, feedback="Falsch.")
    [call] = await _calls(db_session)
    assert (call.feature, call.model, call.batch) == (Feature.verify, "claude-sonnet-5-5", True)
    assert call.cost_usd == Decimal("0.002000")


@pytest.mark.parametrize(
    "result",
    [
        {
            "type": "errored",
            "error": {
                "type": "error",
                "error": {"type": "overloaded_error", "message": "überlastet"},
            },
        },
        {"type": "expired"},
        {"type": "canceled"},
    ],
)
async def test_collect_failed_result_is_unavailable(db_session, result, caplog):
    api = Api(
        httpx2.Response(200, json=_batch("ended")),
        httpx2.Response(200, json=_batch("ended")),
        _results(result),
    )
    with pytest.raises(LLMUnavailable) as raised:
        await _collect(db_session, api)
    assert raised.value.reason.startswith("Der Batch ")
    if result["type"] == "errored":
        assert raised.value.reason == "Der Batch ist fehlgeschlagen."
        assert "überlastet" in caplog.text


async def test_collect_refusal_is_unavailable(db_session):
    message = _message("", stop_reason="refusal", model="claude-sonnet-5-5")
    api = Api(
        httpx2.Response(200, json=_batch("ended")),
        httpx2.Response(200, json=_batch("ended")),
        _results({"type": "succeeded", "message": message}),
    )
    with pytest.raises(LLMUnavailable):
        await _collect(db_session, api)
    assert len(await _calls(db_session)) == 1


async def test_collect_treats_a_network_error_as_still_processing(db_session):
    api = Api(httpx2.ConnectError("keine Verbindung"))
    assert await _collect(db_session, api) is None
