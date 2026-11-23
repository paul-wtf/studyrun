from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator


class McItem(BaseModel):
    kind: Literal["mc"]
    prompt: str
    options: list[str] = Field(min_length=3, max_length=5)
    answer_index: int
    explanation: str
    source_page: int


class TrueFalseItem(BaseModel):
    kind: Literal["true_false"]
    statement: str
    correct: bool
    explanation: str
    source_page: int


class ClozeItem(BaseModel):
    kind: Literal["cloze"]
    text: str
    answers: list[str] = Field(min_length=1)
    explanation: str
    source_page: int


class FreeItem(BaseModel):
    kind: Literal["free"]
    prompt: str
    model_answer: str
    rubric: list[str] = Field(min_length=1, max_length=5)
    source_excerpt: str = Field(max_length=600)
    source_page: int


ItemUnion = Annotated[McItem | TrueFalseItem | ClozeItem | FreeItem, Field(discriminator="kind")]

_ITEM: TypeAdapter[ItemUnion] = TypeAdapter(ItemUnion)


class Concept(BaseModel):
    term: str
    explanation: str


class ChapterContent(BaseModel):
    no_content: bool = False
    summary: str
    concepts: list[Concept]
    items: list[ItemUnion]

    @field_validator("items", mode="before")
    @classmethod
    def _drop_malformed(cls, value: Any) -> Any:
        # Structured outputs cannot enforce maxItems or maxLength, so one item over a
        # limit would otherwise sink the whole chapter.
        if not isinstance(value, list):
            return value
        kept = []
        for entry in value:
            try:
                kept.append(_ITEM.validate_python(entry))
            except ValidationError:
                continue
        return kept


class Verdict(BaseModel):
    index: int
    correct: bool
    in_source: bool
    note: str


class Verification(BaseModel):
    verdicts: list[Verdict]
