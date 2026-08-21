from __future__ import annotations

from datetime import datetime

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_admin: bool = False
    date_created: datetime


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9 _-]+$")
    pin: str = Field(min_length=4, max_length=20)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Name must not be empty or whitespace only")
            return stripped
        return v


class AccountLogin(BaseModel):
    account_id: int
    pin: str


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    choice_a: str
    choice_b: str
    choice_c: str
    choice_d: str
    choice_e: str | None = None
    answer: int | None = None
    solution: str | None = None
    flagged: bool
    active: bool
    account_id: int | None = None
    author_name: str | None = None
    tags: list[str] = []
    date_created: datetime


class QuestionWrite(BaseModel):
    question_text: str
    choice_a: str
    choice_b: str
    choice_c: str
    choice_d: str
    choice_e: str | None = None
    answer: int | None = None
    solution: str | None = None
    active: bool = True
    tags: list[str] = []


class ConstantItem(BaseModel):
    name: str
    value: str
    unit: str = ""
    is_private: bool = False


class ConstantBlock(BaseModel):
    type: Literal["constants"]
    id: int | None = None
    constants: list[ConstantItem]


class FormulaBlock(BaseModel):
    type: Literal["formula"]
    id: int | None = None
    latex: str
    result: str | None = None


class AnswerBlock(BaseModel):
    type: Literal["answer"]
    id: int | None = None
    variable: str
    unit: str = ""
    result: str | None = None


class LegacyAnswerBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: int


Block = Union[ConstantBlock, FormulaBlock, AnswerBlock, LegacyAnswerBlock]


class SolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    account_id: int
    convention: str
    blocks: str


class SolutionWrite(BaseModel):
    convention: Literal["metric", "english", "custom", "imperial"] = "metric"
    blocks: str = "[]"


class SolutionWithAccount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    account_id: int
    account_name: str
    convention: str
    blocks: str
    date_created: datetime


class PaginatedQuestions(BaseModel):
    """Envelope for paginated questions (used when ?envelope=true)."""

    items: list[QuestionOut]
    total: int
    page: int
    per_page: int
