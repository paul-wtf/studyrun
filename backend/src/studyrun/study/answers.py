from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from studyrun.models.db import Item, ItemKind

_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class ObjectiveResult:
    correct: bool
    expected: str
    explanation: str


def normalize_cloze(text: str) -> str:
    out = " ".join(text.casefold().split()).replace("ß", "ss").rstrip(".,;:").rstrip()
    if _NUMBER.fullmatch(out):
        out = out.replace(",", ".")
    return out


def expected_answer(item: Item) -> str:
    payload = item.payload
    if item.kind == ItemKind.mc:
        return str(payload["options"][payload["answer_index"]])
    if item.kind == ItemKind.true_false:
        return "Wahr" if payload["correct"] else "Falsch"
    if item.kind == ItemKind.cloze:
        return str(payload["answers"][0])
    raise ValueError(f"{item.kind.value} items are graded, not checked")


def check_objective(item: Item, answer: dict[str, Any]) -> ObjectiveResult:
    payload = item.payload
    explanation = str(payload.get("explanation", ""))
    if item.kind == ItemKind.mc:
        choice = answer.get("choice")
        if not isinstance(choice, int) or isinstance(choice, bool):
            raise ValueError("choice must be an integer")
        correct = choice == payload["answer_index"]
    elif item.kind == ItemKind.true_false:
        value = answer.get("value")
        if not isinstance(value, bool):
            raise ValueError("value must be a boolean")
        correct = value == payload["correct"]
    elif item.kind == ItemKind.cloze:
        text = answer.get("text")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        correct = normalize_cloze(text) in {normalize_cloze(a) for a in payload["answers"]}
    else:
        raise ValueError(f"{item.kind.value} items are graded, not checked")
    return ObjectiveResult(correct, expected_answer(item), explanation)


def public_view(item: Item) -> dict[str, Any]:
    payload = item.payload
    view: dict[str, Any] = {"id": item.id, "kind": item.kind.value}
    if item.kind == ItemKind.mc:
        view |= {"prompt": payload["prompt"], "options": payload["options"]}
    elif item.kind == ItemKind.true_false:
        view["statement"] = payload["statement"]
    elif item.kind == ItemKind.cloze:
        view["text"] = payload["text"]
    else:
        view["prompt"] = payload["prompt"]
    return view
