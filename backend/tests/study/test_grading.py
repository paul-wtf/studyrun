from datetime import UTC, datetime

from fakes import FakeLLM
from study.helpers import make_chapter, make_item, make_module

from studyrun.models.db import Feature, ItemKind
from studyrun.study.grading import GradeResult, grade_free
from studyrun.study.scheduling import rating_for_score

NOW = datetime(2026, 11, 23, 10, tzinfo=UTC)

PAYLOAD = {
    "prompt": "Was besagt das Ohmsche Gesetz?",
    "model_answer": "U = R * I",
    "rubric": ["Nennt U = R * I", "Nennt die Proportionalitaet"],
    "source_excerpt": "Spannung und Strom sind proportional.",
}


async def _free(db_session):
    chapter = await make_chapter(db_session, await make_module(db_session))
    return await make_item(db_session, chapter, ItemKind.free, payload=PAYLOAD)


async def test_grade_maps_score_to_rating(db_session):
    item = await _free(db_session)
    llm = FakeLLM([GradeResult(score=80, feedback="Gut.", missing=["Proportionalitaet"])])
    result = await grade_free(db_session, llm, item, "U ist R mal I", NOW)
    assert result.score == 80
    assert result.missing == ["Proportionalitaet"]
    assert rating_for_score(result.score).name == "Good"
    assert llm.calls[0].feature == Feature.grade


async def test_grade_clamps_score(db_session):
    item = await _free(db_session)
    llm = FakeLLM([GradeResult(score=140, feedback="", missing=[])])
    assert (await grade_free(db_session, llm, item, "x", NOW)).score == 100


async def test_grade_prompt_has_excerpt_not_pdf(db_session):
    item = await _free(db_session)
    llm = FakeLLM([GradeResult(score=10, feedback="", missing=[])])
    await grade_free(db_session, llm, item, "meine Antwort", NOW)
    content = llm.calls[0].content
    assert [block["type"] for block in content] == ["text"]
    text = content[0]["text"]
    for part in (
        PAYLOAD["prompt"],
        PAYLOAD["model_answer"],
        PAYLOAD["rubric"][1],
        PAYLOAD["source_excerpt"],
        "meine Antwort",
    ):
        assert part in text
