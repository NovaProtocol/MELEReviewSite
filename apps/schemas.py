from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    pdf_hash: str
    question_count: int
    answered_count: int
    date_created: datetime


class SourceList(BaseModel):
    data: list[SourceOut]


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    question_text: str
    choice_a: str
    choice_b: str
    choice_c: str
    choice_d: str
    choice_e: Optional[str] = None
    answer: Optional[int] = None
    solution: Optional[str] = None


class QuestionList(BaseModel):
    data: list[QuestionOut]


class QuestionCreate(BaseModel):
    question_text: str
    choice_a: str
    choice_b: str
    choice_c: str
    choice_d: str
    choice_e: Optional[str] = None
    answer: Optional[int] = None


class SolutionUpdate(BaseModel):
    solution: str


class AnswerUpdate(BaseModel):
    answer: int
