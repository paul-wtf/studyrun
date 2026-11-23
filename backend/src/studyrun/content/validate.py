from __future__ import annotations

import re
from collections.abc import Iterable

from studyrun.content.schemas import ClozeItem, FreeItem, ItemUnion, McItem, TrueFalseItem

GAP = "___"
_UNDERSCORES = re.compile(r"_{3,}")


def _texts(item: ItemUnion) -> list[str]:
    match item:
        case McItem():
            return [item.prompt, item.explanation, *item.options]
        case TrueFalseItem():
            return [item.statement, item.explanation]
        case ClozeItem():
            return [item.text, item.explanation, *item.answers]
        case FreeItem():
            return [item.prompt, item.model_answer, item.source_excerpt, *item.rubric]


def _valid(item: ItemUnion, first_page: int, last_page: int) -> bool:
    if not first_page <= item.source_page <= last_page:
        return False
    if any(not text.strip() for text in _texts(item)):
        return False
    if isinstance(item, McItem):
        if not 0 <= item.answer_index < len(item.options):
            return False
        normalized = {option.strip().casefold() for option in item.options}
        if len(normalized) != len(item.options):
            return False
    return not isinstance(item, ClozeItem) or _UNDERSCORES.findall(item.text) == [GAP]


def validate_items(items: Iterable[ItemUnion], first_page: int, last_page: int) -> list[ItemUnion]:
    return [item for item in items if _valid(item, first_page, last_page)]
