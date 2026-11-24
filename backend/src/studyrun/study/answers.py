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


def check_objective(item: Item, answer: dict[str, Any]) -> ObjectiveResult:
    payload = item.payload
    explanation = str(payload.get("explanation", ""))
    if item.kind == ItemKind.mc:
        choice = answer.get("choice")
        if not isinstance(choice, int) or isinstance(choice, bool):
            raise ValueError("choice must be an integer")
        index = payload["answer_index"]
        return ObjectiveResult(choice == index, payload["options"][index], explanation)
    if item.kind == ItemKind.true_false:
        value = answer.get("value")
        if not isinstance(value, bool):
            raise ValueError("value must be a boolean")
        expected = payload["correct"]
        return ObjectiveResult(value == expected, "Wahr" if expected else "Falsch", explanation)
    if item.kind == ItemKind.cloze:
        text = answer.get("text")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        accepted = payload["answers"]
        correct = normalize_cloze(text) in {normalize_cloze(a) for a in accepted}
        return ObjectiveResult(correct, accepted[0], explanation)
    raise ValueError(f"{item.kind.value} items are graded, not checked")


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
