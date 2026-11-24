from datetime import UTC, datetime

import pytest
from fsrs import Rating
from helpers import make_chapter, make_item, make_module
from sqlalchemy import select

from studyrun.models.db import ReviewLog, ReviewState
from studyrun.study.scheduling import rating_for_objective, rating_for_score, record_review

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("score", "rating"),
    [
        (49, Rating.Again),
        (50, Rating.Hard),
        (74, Rating.Hard),
        (75, Rating.Good),
        (89, Rating.Good),
        (90, Rating.Easy),
    ],
)
def test_rating_for_score_bounds(score, rating):
    assert rating_for_score(score) == rating


def test_rating_for_objective():
    assert rating_for_objective(True) == Rating.Good
    assert rating_for_objective(False) == Rating.Again


async def _item(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module)
    return await make_item(db_session, chapter)


async def test_record_review_creates_state_and_log(db_session):
    item = await _item(db_session)
    await record_review(db_session, item.id, Rating.Good, NOW, correct=True, score=None)

    state = await db_session.get(ReviewState, item.id)
    assert state is not None
    assert state.due > NOW
    assert state.last_review == NOW
    logs = (await db_session.scalars(select(ReviewLog))).all()
    assert [(log.item_id, log.rating, log.correct, log.score) for log in logs] == [
        (item.id, int(Rating.Good), True, None)
    ]

    first_due = state.due
    await record_review(db_session, item.id, Rating.Good, first_due, correct=True, score=None)
    await db_session.refresh(state)
    assert state.due > first_due
    assert len((await db_session.scalars(select(ReviewLog))).all()) == 2


async def test_again_due_sooner_than_easy(db_session):
    module = await make_module(db_session)
    chapter = await make_chapter(db_session, module)
    again = await make_item(db_session, chapter)
    easy = await make_item(db_session, chapter)
    await record_review(db_session, again.id, Rating.Again, NOW, correct=False, score=None)
    await record_review(db_session, easy.id, Rating.Easy, NOW, correct=None, score=95)

    due_again = (await db_session.get(ReviewState, again.id)).due
    due_easy = (await db_session.get(ReviewState, easy.id)).due
    assert due_again < due_easy
