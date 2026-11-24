from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fsrs import Card, Rating, Scheduler
from sqlalchemy.ext.asyncio import AsyncSession

from studyrun.models.db import ReviewLog, ReviewState


def retrievability(card: dict[str, Any] | None, now: datetime) -> float:
    if not card:
        return 0.0
    return Scheduler().get_card_retrievability(Card.from_dict(cast(Any, card)), now)


def rating_for_objective(correct: bool) -> Rating:
    return Rating.Good if correct else Rating.Again


def rating_for_score(score: int) -> Rating:
    if score < 50:
        return Rating.Again
    if score < 75:
        return Rating.Hard
    if score < 90:
        return Rating.Good
    return Rating.Easy


async def record_review(
    session: AsyncSession,
    item_id: int,
    rating: Rating,
    now: datetime,
    *,
    correct: bool | None,
    score: int | None,
) -> None:
    state = await session.get(ReviewState, item_id)
    card = Card.from_dict(cast(Any, state.card)) if state else Card()
    card, _ = Scheduler().review_card(card, rating, now)
    card_json = cast(dict[str, Any], card.to_dict())
    if state is None:
        state = ReviewState(item_id=item_id, card=card_json, due=card.due, last_review=now)
        session.add(state)
    else:
        state.card = card_json
        state.due = card.due
        state.last_review = now
    session.add(
        ReviewLog(
            item_id=item_id, rating=int(rating), correct=correct, score=score, answered_at=now
        )
    )
    await session.flush()
