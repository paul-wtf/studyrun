import pytest
from study.helpers import make_chapter, make_item, make_module

from studyrun.models.db import ItemKind
from studyrun.study.answers import check_objective, normalize_cloze, public_view


async def _item(db_session, kind, payload):
    chapter = await make_chapter(db_session, await make_module(db_session))
    return await make_item(db_session, chapter, kind, payload=payload)


async def test_mc_correct_and_wrong(db_session):
    item = await _item(
        db_session,
        ItemKind.mc,
        {"prompt": "Q", "options": ["a", "b", "c"], "answer_index": 1, "explanation": "weil"},
    )
    right = check_objective(item, {"choice": 1})
    assert (right.correct, right.expected, right.explanation) == (True, "b", "weil")
    assert check_objective(item, {"choice": 0}).correct is False
    with pytest.raises(ValueError):
        check_objective(item, {"choice": "1"})


async def test_true_false(db_session):
    item = await _item(
        db_session,
        ItemKind.true_false,
        {"statement": "S", "correct": False, "explanation": "weil"},
    )
    assert check_objective(item, {"value": False}).correct is True
    wrong = check_objective(item, {"value": True})
    assert (wrong.correct, wrong.expected) == (False, "Falsch")
    with pytest.raises(ValueError):
        check_objective(item, {"value": "nein"})


async def test_cloze_normalization(db_session):
    assert normalize_cloze("Ohmsches Gesetz ") == normalize_cloze("ohmsches gesetz")
    assert normalize_cloze("Maß") == normalize_cloze("Mass")
    assert normalize_cloze("0,5") == normalize_cloze("0.5")
    assert normalize_cloze("5") != normalize_cloze("0.5")
    assert normalize_cloze("  Ohm\t Gesetz. ") == "ohm gesetz"

    item = await _item(
        db_session,
        ItemKind.cloze,
        {"text": "Das ___ Gesetz", "answers": ["Ohmsches", "Ohm'sches"], "explanation": "e"},
    )
    assert check_objective(item, {"text": "ohmsches."}).correct is True
    assert check_objective(item, {"text": "Ohm'sches"}).correct is True
    miss = check_objective(item, {"text": "Kirchhoff"})
    assert (miss.correct, miss.expected) == (False, "Ohmsches")


async def test_free_items_are_not_checked_locally(db_session):
    item = await _item(db_session, ItemKind.free, {"prompt": "Q"})
    with pytest.raises(ValueError):
        check_objective(item, {"text": "x"})


async def test_public_view_hides_answers(db_session):
    mc = await _item(
        db_session,
        ItemKind.mc,
        {"prompt": "Q", "options": ["a", "b", "c"], "answer_index": 1, "explanation": "weil"},
    )
    assert public_view(mc) == {"id": mc.id, "kind": "mc", "prompt": "Q", "options": ["a", "b", "c"]}
    free = await _item(
        db_session,
        ItemKind.free,
        {"prompt": "Q", "model_answer": "M", "rubric": ["r"], "source_excerpt": "x"},
    )
    assert public_view(free) == {"id": free.id, "kind": "free", "prompt": "Q"}
