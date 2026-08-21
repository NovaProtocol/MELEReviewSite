from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class SolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    account_id: int
    convention: str
    blocks: str


class SolutionWrite(BaseModel):
    convention: str = "metric"
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
