from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fakes import FakeLLM
from sqlalchemy import select
from study.helpers import make_chapter, make_item, make_module

from studyrun.ai.budget import BudgetExceeded
from studyrun.ai.llm import LLMUnavailable
from studyrun.deps import get_llm, get_now
from studyrun.models.db import (
    Feature,
    FlagReason,
    ItemKind,
    ItemStatus,
    ReviewLog,
    ReviewState,
)
from studyrun.study.grading import GradeResult

BERLIN = ZoneInfo("Europe/Berlin")

MC = {"prompt": "Q?", "options": ["a", "b", "c"], "answer_index": 2, "explanation": "weil c"}
FREE = {
    "prompt": "Erklaere.",
    "model_answer": "Muster",
    "rubric": ["r1"],
    "source_excerpt": "Auszug",
}


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


def use_llm(api, responses) -> FakeLLM:
    _, app = api
    llm = FakeLLM(responses)
    app.dependency_overrides[get_llm] = lambda: llm
    return llm


async def seed(db_session, *, introduced: bool = False):
    module = await make_module(db_session)
    chapter = await make_chapter(
        db_session, module, introduced_at=berlin(20, 9) if introduced else None
    )
    chapter.summary = "Zusammenfassung"
    chapter.concepts = [{"term": "Strom", "explanation": "Fluss"}]
    mc = await make_item(db_session, chapter, ItemKind.mc, payload=MC)
    free = await make_item(db_session, chapter, ItemKind.free, payload=FREE)
    return chapter, mc, free


def index_of(run, kind_id: int, key="item") -> int:
    return next(e["n"] for e in run["entries"] if key in e and e[key]["id"] == kind_id)


async def start(client):
    resp = await client.post("/api/runs")
    assert resp.status_code == 200
    return resp.json()


async def test_run_resumes_same_berlin_day(api, db_session, clock):
    client, _ = api
    await seed(db_session)
    clock.now = berlin(23, 23, 30)
    first = await start(client)
    clock.now = berlin(23, 23, 50)
    assert (await start(client))["id"] == first["id"]
    clock.now = berlin(24, 0, 10)
    assert (await start(client))["id"] != first["id"]


async def test_finished_run_is_not_resumed(api, db_session, clock):
    client, _ = api
    await seed(db_session)
    first = await start(client)
    await client.post(f"/api/runs/{first['id']}/finish")
    assert (await start(client))["id"] != first["id"]


async def test_run_entries_carry_links(api, db_session, clock):
    client, _ = api
    chapter, mc, _ = await seed(db_session)
    run = await start(client)
    intro = next(e for e in run["entries"] if e["type"] == "intro")
    assert intro["done"] is False
    assert intro["chapter"]["title"] == chapter.title
    assert intro["chapter"]["summary"] == "Zusammenfassung"
    assert intro["chapter"]["concepts"] == [{"term": "Strom", "explanation": "Fluss"}]
    assert intro["chapter"]["source"] == f"/api/booklets/{chapter.booklet_id}/pdf#page=1"
    entry = run["entries"][index_of(run, mc.id)]
    assert entry["item"]["source"] == f"/api/booklets/{chapter.booklet_id}/pdf#page=1"


async def test_public_view_hides_answers(api, db_session, clock):
    client, _ = api
    await seed(db_session)
    run = await start(client)
    items = [e["item"] for e in run["entries"] if e["type"] == "item"]
    assert len(items) == 2
    for item in items:
        assert set(item) <= {"id", "kind", "prompt", "options", "source"}
    text = str(run)
    assert "weil c" not in text and "Muster" not in text and "Auszug" not in text


async def test_ack_introduces_chapter(api, db_session, clock):
    client, _ = api
    chapter, _, _ = await seed(db_session)
    run = await start(client)
    n = next(e["n"] for e in run["entries"] if e["type"] == "intro")
    resp = await client.post(f"/api/runs/{run['id']}/entries/{n}/ack")
    assert resp.status_code == 200
    await db_session.refresh(chapter)
    assert chapter.introduced_at == clock.now
    again = await start(client)
    assert again["entries"][n]["done"] is True

    item_n = next(e["n"] for e in run["entries"] if e["type"] == "item")
    assert (await client.post(f"/api/runs/{run['id']}/entries/{item_n}/ack")).status_code == 409


async def test_objective_answer_records_review(api, db_session, clock):
    client, _ = api
    _, mc, _ = await seed(db_session)
    run = await start(client)
    n = index_of(run, mc.id)
    resp = await client.post(
        f"/api/runs/{run['id']}/entries/{n}/answer", json={"answer": {"choice": 2}}
    )
    assert resp.json() == {"correct": True, "expected": "c", "explanation": "weil c"}
    log = (await db_session.scalars(select(ReviewLog).where(ReviewLog.item_id == mc.id))).one()
    assert (log.correct, log.rating, log.score) == (True, 3, None)
    assert await db_session.get(ReviewState, mc.id) is not None
    assert (await start(client))["entries"][n]["done"] is True


async def test_objective_answer_wrong_shape(api, db_session, clock):
    client, _ = api
    _, mc, _ = await seed(db_session)
    run = await start(client)
    n = index_of(run, mc.id)
    resp = await client.post(
        f"/api/runs/{run['id']}/entries/{n}/answer", json={"answer": {"choice": "x"}}
    )
    assert resp.status_code == 422


async def test_free_answer_graded(api, db_session, clock):
    client, _ = api
    _, _, free = await seed(db_session)
    llm = use_llm(api, [GradeResult(score=92, feedback="Sehr gut.", missing=[])])
    run = await start(client)
    n = index_of(run, free.id)
    resp = await client.post(
        f"/api/runs/{run['id']}/entries/{n}/answer", json={"answer": {"text": "meine"}}
    )
    assert resp.json() == {
        "score": 92,
        "feedback": "Sehr gut.",
        "missing": [],
        "model_answer": "Muster",
    }
    assert llm.calls[0].feature == Feature.grade
    log = (await db_session.scalars(select(ReviewLog).where(ReviewLog.item_id == free.id))).one()
    assert (log.rating, log.score) == (4, 92)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (BudgetExceeded(Feature.grade, 1, 1), "Tagesbudget erreicht"),
        (LLMUnavailable("down"), "Bewertung gerade nicht moeglich"),
    ],
)
async def test_free_answer_grading_unavailable_offers_self_rating(
    api, db_session, clock, error, reason
):
    client, _ = api
    _, _, free = await seed(db_session)
    use_llm(api, [error])
    run = await start(client)
    n = index_of(run, free.id)
    resp = await client.post(
        f"/api/runs/{run['id']}/entries/{n}/answer", json={"answer": {"text": "meine"}}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "grading_unavailable": True,
        "reason": reason,
        "model_answer": "Muster",
    }
    assert await db_session.get(ReviewState, free.id) is None
    assert (await start(client))["entries"][n]["grading_unavailable"] is True

    rated = await client.post(
        f"/api/runs/{run['id']}/entries/{n}/self-rate", json={"rating": "good"}
    )
    assert rated.status_code == 200
    log = (await db_session.scalars(select(ReviewLog).where(ReviewLog.item_id == free.id))).one()
    assert (log.rating, log.correct, log.score) == (3, True, None)
    assert (await start(client))["entries"][n]["done"] is True


async def test_self_rate_again(api, db_session, clock):
    client, _ = api
    _, _, free = await seed(db_session)
    use_llm(api, [LLMUnavailable("x")])
    run = await start(client)
    n = index_of(run, free.id)
    await client.post(f"/api/runs/{run['id']}/entries/{n}/answer", json={"answer": {"text": "t"}})
    await client.post(f"/api/runs/{run['id']}/entries/{n}/self-rate", json={"rating": "again"})
    log = (await db_session.scalars(select(ReviewLog).where(ReviewLog.item_id == free.id))).one()
    assert (log.rating, log.correct) == (1, False)


async def test_self_rate_rejected_without_grading_failure(api, db_session, clock):
    client, _ = api
    _, mc, free = await seed(db_session)
    use_llm(api, [])
    run = await start(client)
    for item in (mc, free):
        n = index_of(run, item.id)
        resp = await client.post(
            f"/api/runs/{run['id']}/entries/{n}/self-rate", json={"rating": "good"}
        )
        assert resp.status_code == 409
    assert (await db_session.scalars(select(ReviewLog))).all() == []


async def test_answer_twice_conflicts(api, db_session, clock):
    client, _ = api
    _, mc, _ = await seed(db_session)
    run = await start(client)
    n = index_of(run, mc.id)
    url = f"/api/runs/{run['id']}/entries/{n}/answer"
    assert (await client.post(url, json={"answer": {"choice": 0}})).status_code == 200
    assert (await client.post(url, json={"answer": {"choice": 2}})).status_code == 409
    assert len((await db_session.scalars(select(ReviewLog))).all()) == 1


async def test_unknown_run_and_entry(api, db_session, clock):
    client, _ = api
    await seed(db_session)
    run = await start(client)
    assert (await client.post("/api/runs/9999/finish")).status_code == 404
    resp = await client.post(f"/api/runs/{run['id']}/entries/99/answer", json={"answer": {}})
    assert resp.status_code == 404


async def test_finish_partial_run(api, db_session, clock):
    client, _ = api
    chapter, mc, _ = await seed(db_session)
    use_llm(api, [])
    run = await start(client)
    intro_n = next(e["n"] for e in run["entries"] if e["type"] == "intro")
    await client.post(f"/api/runs/{run['id']}/entries/{intro_n}/ack")
    n = index_of(run, mc.id)
    await client.post(f"/api/runs/{run['id']}/entries/{n}/answer", json={"answer": {"choice": 2}})

    other = await make_item(db_session, chapter, ItemKind.mc, payload=MC)
    db_session.add(
        ReviewState(
            item_id=other.id,
            card={},
            due=berlin(24, 12),
            last_review=None,
        )
    )
    soon = await make_item(db_session, chapter, ItemKind.mc, payload=MC)
    db_session.add(ReviewState(item_id=soon.id, card={}, due=berlin(23, 20), last_review=None))
    later = await make_item(db_session, chapter, ItemKind.mc, payload=MC)
    db_session.add(ReviewState(item_id=later.id, card={}, due=berlin(26, 12), last_review=None))
    await db_session.flush()

    resp = await client.post(f"/api/runs/{run['id']}/finish")
    assert resp.status_code == 200
    body = resp.json()
    assert body["answered"] == 1
    assert body["correct"] == 1
    assert body["chapters_introduced"] == [chapter.title]
    assert body["due_tomorrow"] == 1
    assert (await db_session.scalars(select(ReviewLog))).all().__len__() == 1


async def test_flag_removes_from_next_run(api, db_session, clock):
    client, _ = api
    _, mc, free = await seed(db_session, introduced=True)
    first = await start(client)
    assert index_of(first, mc.id) >= 0
    resp = await client.post(f"/api/items/{mc.id}/flag", json={"reason": "wrong"})
    assert resp.status_code == 200
    await db_session.refresh(mc)
    assert (mc.status, mc.flag_reason) == (ItemStatus.flagged, FlagReason.wrong)

    await client.post(f"/api/runs/{first['id']}/finish")
    second = await start(client)
    ids = [e["item"]["id"] for e in second["entries"] if e["type"] == "item"]
    assert mc.id not in ids
    assert free.id in ids


async def test_flag_unknown_item_and_reason(api, db_session):
    client, _ = api
    assert (await client.post("/api/items/999/flag", json={"reason": "wrong"})).status_code == 404
    _, mc, _ = await seed(db_session)
    assert (
        await client.post(f"/api/items/{mc.id}/flag", json={"reason": "bogus"})
    ).status_code == 422
