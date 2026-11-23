from builders import cloze, free, mc, true_false

from studyrun.content.validate import validate_items


def test_drops_page_out_of_range():
    items = [mc(page=1), mc(page=3), free(page=6), true_false(page=7)]
    assert validate_items(items, 3, 6) == [items[1], items[2]]


def test_drops_bad_answer_index():
    items = [mc(answer_index=3), mc(answer_index=-1), mc(answer_index=2)]
    assert validate_items(items, 1, 9) == [items[2]]


def test_drops_duplicate_options():
    items = [
        mc(options=["Blau", " blau ", "Rot"]),
        mc(options=["Blau", "Grün", "GRÜN", "Rot"]),
        mc(options=["Blau", "Blaugrün", "Rot"]),
    ]
    assert validate_items(items, 1, 9) == [items[2]]


def test_drops_cloze_without_single_gap():
    items = [
        cloze(text="Der Testvogel frisst Körner."),
        cloze(text="Der ___ frisst ___."),
        cloze(text="Der Testvogel frisst ____."),
        cloze(text="___ frisst der Testvogel."),
    ]
    assert validate_items(items, 1, 9) == [items[3]]


def test_drops_empty_strings():
    items = [
        mc(prompt="  "),
        mc(options=["Blau", "", "Rot"]),
        true_false(explanation=""),
        cloze(answers=["Körner", " "]),
        free(model_answer=""),
        free(rubric=["nennt das Gefieder", ""]),
        free(source_excerpt="   "),
        mc(),
    ]
    assert validate_items(items, 1, 9) == [items[-1]]


def test_keeps_valid_items():
    items = [mc(page=2), true_false(page=3), cloze(page=4), free(page=5)]
    assert validate_items(items, 2, 5) == items
