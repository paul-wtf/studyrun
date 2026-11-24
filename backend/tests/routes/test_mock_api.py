from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fakes import FakeLLM
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from study.helpers import make_chapter, make_item, make_module, make_subject

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.ledger import record_call
from studyrun.ai.llm import LLMUnavailable
from studyrun.ai.pricing import Usage
from studyrun.deps import get_llm, get_now, get_session
from studyrun.models.db import (
    ApiCall,
    ChapterStatus,
    Feature,
    ItemKind,
    MockExam,
    Module,
    ReviewLog,
)
from studyrun.routes import mock as mock_routes
from studyrun.study.grading import GradeResult

BERLIN = ZoneInfo("Europe/Berlin")

MC = {"prompt": "Q?", "options": ["a", "b", "c"], "answer_index": 2, "explanation": "weil c"}
TF = {"statement": "Wasser ist nass.", "correct": True, "explanation": "ja"}
CLOZE = {"text": "Die Antwort ist ___.", "answers": ["42"], "explanation": "Douglas"}
FREE = {
    "prompt": "Erklaere.",
    "model_answer": "Muster",
    "rubric": ["r1"],
    "source_excerpt": "Auszug",
}
SECRET_KEYS = {"answer_index", "correct", "answers", "model_answer", "explanation", "rubric"}


def berlin(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=BERLIN).astimezone(UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(api):
    _, app = api
    clock = Clock(berlin(23, 10))
    app.dependency_overrides[get_now] = clock
    return clock


@pytest.fixture
def llm(api):
    _, app = api
    fake = FakeLLM([])
    app.dependency_overrides[get_llm] = lambda: fake
    return fake


async def seed(db_session, *, free_items: int = 1):
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    first = await make_chapter(db_session, module, 0, introduced_at=berlin(20, 9))
    second = await make_chapter(db_session, module, 1, introduced_at=berlin(20, 9))
    items = {
        "mc": await make_item(db_session, first, ItemKind.mc, payload=MC),
        "tf": await make_item(db_session, first, ItemKind.true_false, payload=TF),
        "cloze": await make_item(db_session, second, ItemKind.cloze, payload=CLOZE),
    }
    for i in range(free_items):
        items[f"free{i}"] = await make_item(db_session, second, ItemKind.free, payload=FREE)
    return subject, (first, second), items


def n_of(mock, item) -> int:
    return next(e["n"] for e in mock["entries"] if e["item"]["id"] == item.id)


async def start(client, subject):
    resp = await client.post(f"/api/subjects/{subject.id}/mock")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def reviews(db_session) -> int:
    return await db_session.scalar(select(func.count()).select_from(ReviewLog)) or 0


async def test_locked_subject_refuses_a_mock(api, db_session, clock, llm):
    client, _ = api
    module = await make_module(db_session)
    subject = await make_subject(db_session, "Alpha", modules=(module,))
    empty = await make_subject(db_session, "Leer")
    for index in range(3):
        await make_chapter(db_session, module, index, introduced_at=berlin(20, 9))
    await make_chapter(db_session, module, 3)

    assert (await client.post(f"/api/subjects/{subject.id}/mock")).status_code == 409
    assert (await client.post(f"/api/subjects/{empty.id}/mock")).status_code == 409
    assert (await client.post("/api/subjects/999/mock")).status_code == 404
    out = (await client.get(f"/api/subjects/{subject.id}")).json()
    assert out["unlocked"] is False
    assert out["introduced_share"] == 0.75
    assert (await client.get(f"/api/subjects/{empty.id}")).json()["unlocked"] is False


async def test_skipped_chapters_do_not_count_against_the_unlock(api, db_session, clock, llm):
    client, _ = api
    subject, _, _ = await seed(db_session)
    module_id = (await client.get(f"/api/subjects/{subject.id}")).json()["module_ids"][0]
    module = await db_session.get(Module, module_id)
    for index in range(2, 5):
        await make_chapter(db_session, module, index, status=ChapterStatus.skipped)

    out = (await client.get(f"/api/subjects/{subject.id}")).json()
    assert out["unlocked"] is True
    assert out["introduced_share"] == 1.0


async def test_mock_shows_public_views_and_a_deadline(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session)

    mock = await start(client, subject)

    assert mock["subject_id"] == subject.id
    assert datetime.fromisoformat(mock["deadline"]) == clock.now + timedelta(minutes=90)
    assert mock["finished"] is False and mock["expired"] is False and mock["result"] is None
    assert {e["item"]["id"] for e in mock["entries"]} == {i.id for i in items.values()}
    for entry in mock["entries"]:
        assert entry["answered"] is False and entry["answer"] is None and entry["review"] is None
        assert not SECRET_KEYS & set(entry["item"])
        assert "source" not in entry["item"] and entry["source"] is None
    assert (await client.get(f"/api/mock/{mock['id']}")).json() == mock


async def test_answers_get_no_feedback(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session)
    mock = await start(client, subject)
    n = n_of(mock, items["mc"])

    wrong = await client.post(f"/api/mock/{mock['id']}/answers/{n}", json={"answer": {"choice": 0}})
    right = await client.post(f"/api/mock/{mock['id']}/answers/{n}", json={"answer": {"choice": 2}})

    assert wrong.json() == {"n": n, "answered": True}
    assert right.json() == {"n": n, "answered": True}
    entry = (await client.get(f"/api/mock/{mock['id']}")).json()["entries"][n]
    assert entry["answered"] is True
    assert entry["answer"] == {"choice": 2, "value": None, "text": None}
    assert entry["review"] is None
    assert await reviews(db_session) == 0
    bad = await client.post(f"/api/mock/{mock['id']}/answers/{n}", json={"answer": {"text": "x"}})
    assert bad.status_code == 422
    assert (
        await client.post(f"/api/mock/{mock['id']}/answers/99", json={"answer": {"choice": 0}})
    ).status_code == 404


async def test_blank_text_clears_the_answer(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session)
    mock = await start(client, subject)
    n = n_of(mock, items["free0"])

    await client.post(f"/api/mock/{mock['id']}/answers/{n}", json={"answer": {"text": "etwas"}})
    resp = await client.post(f"/api/mock/{mock['id']}/answers/{n}", json={"answer": {"text": " "}})

    assert resp.json() == {"n": n, "answered": False}
    assert (await client.get(f"/api/mock/{mock['id']}")).json()["entries"][n]["answer"] is None


async def test_finish_scores_every_item_and_records_reviews_once(api, db_session, clock, llm):
    client, _ = api
    subject, (first, second), items = await seed(db_session)
    mock = await start(client, subject)
    mid = mock["id"]
    await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['mc'])}", json={"answer": {"choice": 2}}
    )
    await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['cloze'])}", json={"answer": {"text": "41"}}
    )
    await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['free0'])}",
        json={"answer": {"text": "Meine Antwort"}},
    )
    llm.responses.append(GradeResult(score=80, feedback="Fast.", missing=["r1"]))
    clock.now += timedelta(minutes=30)

    resp = await client.post(f"/api/mock/{mid}/finish")

    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["finished"] is True
    result = out["result"]
    assert result["score"] == 45
    assert result["passed"] is False
    assert result["pass_mark"] == 50
    assert result["pending_self_rating"] == 0
    assert result["chapters"] == [
        {"chapter_id": first.id, "title": first.title, "items": 2, "score": 50},
        {"chapter_id": second.id, "title": second.title, "items": 2, "score": 40},
    ]
    assert all(e["source"].startswith("/api/booklets/") for e in out["entries"])
    by_item = {e["item"]["id"]: e["review"] for e in out["entries"]}
    assert by_item[items["mc"].id]["correct"] is True
    assert by_item[items["mc"].id]["score"] == 100
    assert by_item[items["tf"].id] == {
        "score": 0,
        "correct": False,
        "expected": "Wahr",
        "explanation": "ja",
        "feedback": None,
        "missing": [],
        "model_answer": None,
        "grading_unavailable": False,
    }
    assert by_item[items["cloze"].id]["expected"] == "42"
    assert by_item[items["free0"].id]["score"] == 80
    assert by_item[items["free0"].id]["feedback"] == "Fast."
    assert by_item[items["free0"].id]["model_answer"] == "Muster"
    assert len(llm.calls) == 1 and llm.calls[0].feature == Feature.grade
    logs = (await db_session.scalars(select(ReviewLog))).all()
    assert {log.item_id for log in logs} == {items[k].id for k in ("mc", "cloze", "free0")}

    again = await client.post(f"/api/mock/{mid}/finish")
    assert again.json() == out
    assert await reviews(db_session) == 3
    late = await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['tf'])}", json={"answer": {"value": True}}
    )
    assert late.status_code == 409


async def test_passing_follows_the_pass_mark(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session, free_items=0)
    subject.pass_mark = 60
    mock = await start(client, subject)
    for key, answer in [("mc", {"choice": 2}), ("tf", {"value": True})]:
        await client.post(
            f"/api/mock/{mock['id']}/answers/{n_of(mock, items[key])}", json={"answer": answer}
        )

    result = (await client.post(f"/api/mock/{mock['id']}/finish")).json()["result"]

    assert result["score"] == 67
    assert result["passed"] is True
    assert result["pass_mark"] == 60


async def test_time_runs_out(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session, free_items=0)
    mock = await start(client, subject)
    mid = mock["id"]
    await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['mc'])}", json={"answer": {"choice": 2}}
    )
    clock.now += timedelta(minutes=90)

    late = await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['tf'])}", json={"answer": {"value": True}}
    )
    assert late.status_code == 409
    assert late.json()["detail"] == "Zeit abgelaufen"
    current = (await client.get(f"/api/mock/{mid}")).json()
    assert current["expired"] is True and current["finished"] is False
    result = (await client.post(f"/api/mock/{mid}/finish")).json()["result"]
    assert result["score"] == 33
    assert await reviews(db_session) == 1


@pytest.mark.parametrize(
    "error",
    [BudgetExceeded(Feature.grade, Decimal("0.5"), Decimal("0.5")), LLMUnavailable("weg")],
)
async def test_cap_reached_mid_grading_leaves_the_rest_to_self_rating(
    api, db_session, clock, llm, error
):
    client, _ = api
    subject, _, items = await seed(db_session, free_items=3)
    mock = await start(client, subject)
    mid = mock["id"]
    for i in range(3):
        await client.post(
            f"/api/mock/{mid}/answers/{n_of(mock, items[f'free{i}'])}",
            json={"answer": {"text": f"Antwort {i}"}},
        )
    llm.responses += [GradeResult(score=90, feedback="Gut.", missing=[]), error]

    out = (await client.post(f"/api/mock/{mid}/finish")).json()

    assert len(llm.calls) == 2
    reviews_by_item = {e["item"]["id"]: e["review"] for e in out["entries"]}
    graded = [reviews_by_item[items[f"free{i}"].id] for i in range(3)]
    assert [g["score"] for g in graded] == [90, None, None]
    assert [g["grading_unavailable"] for g in graded] == [False, True, True]
    assert graded[1]["model_answer"] == "Muster"
    assert out["result"]["score"] == 15
    assert out["result"]["pending_self_rating"] == 2
    assert await reviews(db_session) == 1

    n1 = n_of(mock, items["free1"])
    rated = await client.post(f"/api/mock/{mid}/self-rate/{n1}", json={"rating": "good"})
    assert rated.status_code == 200, rated.text
    assert rated.json()["result"]["score"] == 32
    assert rated.json()["result"]["pending_self_rating"] == 1
    assert rated.json()["entries"][n1]["review"]["score"] == 100
    assert await reviews(db_session) == 2
    assert (
        await client.post(f"/api/mock/{mid}/self-rate/{n1}", json={"rating": "good"})
    ).status_code == 409
    n0 = n_of(mock, items["free0"])
    assert (
        await client.post(f"/api/mock/{mid}/self-rate/{n0}", json={"rating": "again"})
    ).status_code == 409
    stored = await db_session.get(MockExam, mid)
    await db_session.refresh(stored)
    assert stored.score == 32


async def test_self_rating_needs_a_finished_mock(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session)
    mock = await start(client, subject)
    n = n_of(mock, items["free0"])
    resp = await client.post(f"/api/mock/{mock['id']}/self-rate/{n}", json={"rating": "good"})
    assert resp.status_code == 409


async def test_mock_resumes_after_midnight(api, db_session, clock, llm):
    client, _ = api
    subject, _, _ = await seed(db_session)
    clock.now = berlin(23, 23, 30)
    first = await start(client, subject)
    clock.now = berlin(24, 0, 10)
    assert (await start(client, subject))["id"] == first["id"]


async def test_abandoned_mock_is_finished_before_a_new_one(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session, free_items=0)
    first = await start(client, subject)
    await client.post(
        f"/api/mock/{first['id']}/answers/{n_of(first, items['mc'])}",
        json={"answer": {"choice": 2}},
    )
    clock.now += timedelta(minutes=180)
    assert (await start(client, subject))["id"] == first["id"]

    clock.now += timedelta(minutes=1)
    second = await start(client, subject)

    assert second["id"] != first["id"]
    old = (await client.get(f"/api/mock/{first['id']}")).json()
    assert old["finished"] is True
    assert old["result"]["score"] == 33
    assert await reviews(db_session) == 1


async def test_history_lists_mocks_newest_first(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session, free_items=0)
    first = await start(client, subject)
    await client.post(
        f"/api/mock/{first['id']}/answers/{n_of(first, items['mc'])}",
        json={"answer": {"choice": 2}},
    )
    await client.post(f"/api/mock/{first['id']}/finish")
    clock.now += timedelta(hours=2)
    second = await start(client, subject)

    history = (await client.get(f"/api/subjects/{subject.id}/mocks")).json()

    assert [h["id"] for h in history] == [second["id"], first["id"]]
    assert history[1]["score"] == 33 and history[1]["passed"] is False
    assert history[1]["finished_at"] is not None
    assert history[0]["score"] is None and history[0]["finished_at"] is None
    assert (await client.get("/api/subjects/999/mocks")).status_code == 404
    assert (await client.get("/api/mock/999")).status_code == 404


class LedgerLLM:
    """Writes a ledger row per call, like AnthropicLLM; an exception stands for a kill."""

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def structured(self, *, session, feature, system, content, schema, now):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        await record_call(session, feature, "claude-opus-5-5", Usage(1000, 100, 0, 0), now)
        return response


@pytest.fixture
def committing_session(api, db_session):
    """A request session that commits and rolls back like the real one, inside the
    test transaction (a savepoint per request)."""
    _, app = api

    async def _session():
        factory = async_sessionmaker(
            bind=await db_session.connection(),
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = _session


async def test_interrupted_finish_keeps_paid_grades(api, db_session, clock, committing_session):
    client, app = api
    subject, _, items = await seed(db_session, free_items=3)
    mock = await start(client, subject)
    mid = mock["id"]
    for i in range(3):
        await client.post(
            f"/api/mock/{mid}/answers/{n_of(mock, items[f'free{i}'])}",
            json={"answer": {"text": f"Antwort {i}"}},
        )
    killed = LedgerLLM([GradeResult(score=90, feedback="Gut.", missing=[]), RuntimeError("kill")])
    app.dependency_overrides[get_llm] = lambda: killed

    with pytest.raises(RuntimeError):
        await client.post(f"/api/mock/{mid}/finish")

    assert await db_session.scalar(select(func.count()).select_from(ApiCall)) == 1
    graded = (await client.get(f"/api/mock/{mid}")).json()
    assert graded["finished"] is False
    late = await client.post(
        f"/api/mock/{mid}/answers/{n_of(mock, items['free2'])}", json={"answer": {"text": "neu"}}
    )
    assert late.status_code == 409
    retry = LedgerLLM([GradeResult(score=50, feedback="", missing=[])] * 2)
    app.dependency_overrides[get_llm] = lambda: retry
    out = (await client.post(f"/api/mock/{mid}/finish")).json()
    assert retry.calls == 2
    scores = {e["item"]["id"]: e["review"]["score"] for e in out["entries"]}
    assert [scores[items[f"free{i}"].id] for i in range(3)] == [90, 50, 50]
    assert await db_session.scalar(select(func.count()).select_from(ApiCall)) == 3
    assert await reviews(db_session) == 3


async def test_mock_keeps_its_pass_mark(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session, free_items=0)
    await client.patch(f"/api/subjects/{subject.id}", json={"pass_mark": 60})
    mock = await start(client, subject)
    for key, answer in [("mc", {"choice": 2}), ("tf", {"value": True})]:
        await client.post(
            f"/api/mock/{mock['id']}/answers/{n_of(mock, items[key])}", json={"answer": answer}
        )
    await client.post(f"/api/mock/{mock['id']}/finish")

    await client.patch(f"/api/subjects/{subject.id}", json={"pass_mark": 70})

    result = (await client.get(f"/api/mock/{mock['id']}")).json()["result"]
    assert (result["score"], result["pass_mark"], result["passed"]) == (67, 60, True)
    history = (await client.get(f"/api/subjects/{subject.id}/mocks")).json()
    assert history[0]["passed"] is True


async def test_open_mock_items_stay_out_of_runs(api, db_session, clock, llm):
    client, _ = api
    subject, _, items = await seed(db_session)
    mock = await start(client, subject)
    mock_items = {e["item"]["id"] for e in mock["entries"]}

    assert mock_items == {i.id for i in items.values()}

    run = (await client.post("/api/runs", json={"subject_id": subject.id})).json()

    assert run["id"] is None and run["entries"] == []
    await client.post(f"/api/mock/{mock['id']}/finish")
    later = (await client.post("/api/runs", json={"subject_id": subject.id})).json()
    assert {e["item"]["id"] for e in later["entries"] if e["type"] == "item"} & mock_items


async def test_mock_skips_items_pending_in_open_runs(api, db_session, clock, llm):
    client, _ = api
    subject, (first, _), items = await seed(db_session)
    for i in range(4):
        items[f"tf{i}"] = await make_item(db_session, first, ItemKind.true_false, payload=TF)
    run = (await client.post("/api/runs", json={"subject_id": subject.id})).json()
    pending = {e["item"]["id"] for e in run["entries"] if e["type"] == "item"}
    assert pending

    mock = await start(client, subject)

    assert {e["item"]["id"] for e in mock["entries"]} == {i.id for i in items.values()} - pending


async def test_start_completes_a_half_finished_mock(api, db_session, clock, committing_session):
    client, app = api
    subject, _, items = await seed(db_session, free_items=2)
    mock = await start(client, subject)
    mid = mock["id"]
    for i in range(2):
        await client.post(
            f"/api/mock/{mid}/answers/{n_of(mock, items[f'free{i}'])}",
            json={"answer": {"text": f"Antwort {i}"}},
        )
    killed = LedgerLLM([GradeResult(score=90, feedback="Gut.", missing=[]), RuntimeError("kill")])
    app.dependency_overrides[get_llm] = lambda: killed
    with pytest.raises(RuntimeError):
        await client.post(f"/api/mock/{mid}/finish")

    current = (await client.get(f"/api/mock/{mid}")).json()
    assert (current["finished"], current["finishing"]) == (False, True)
    retry = LedgerLLM([GradeResult(score=50, feedback="", missing=[])])
    app.dependency_overrides[get_llm] = lambda: retry
    resumed = await start(client, subject)

    assert resumed["id"] == mid
    assert (resumed["finished"], resumed["finishing"]) == (True, False)
    assert retry.calls == 1
    assert resumed["result"]["score"] == 28


async def test_runs_get_the_items_of_an_expired_mock_back(api, db_session, clock, llm):
    client, _ = api
    subject, _, _ = await seed(db_session)
    mock = await start(client, subject)
    mock_items = {e["item"]["id"] for e in mock["entries"]}
    clock.now += timedelta(minutes=89)
    assert (await client.post("/api/runs", json={"subject_id": subject.id})).json()["id"] is None

    clock.now += timedelta(minutes=2)
    run = (await client.post("/api/runs", json={"subject_id": subject.id})).json()

    assert {e["item"]["id"] for e in run["entries"] if e["type"] == "item"} & mock_items


async def test_concurrent_start_returns_the_open_mock(api, db_session, clock, llm, monkeypatch):
    client, _ = api
    subject, _, _ = await seed(db_session)
    first = await start(client, subject)
    real = mock_routes._open_mock
    calls = []

    async def raced(session, subject_id):
        calls.append(subject_id)
        return None if len(calls) == 1 else await real(session, subject_id)

    async def unseen(session, settings, now):
        return frozenset()

    # The racing request sees neither the other mock nor its blocked items.
    monkeypatch.setattr(mock_routes, "_open_mock", raced)
    monkeypatch.setattr(mock_routes, "open_items", unseen)

    second = await start(client, subject)

    assert second["id"] == first["id"]
    assert len(calls) == 2
    assert await db_session.scalar(select(func.count()).select_from(MockExam)) == 1
