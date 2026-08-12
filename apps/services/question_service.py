from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.models import Question, Source
from apps.schemas import QuestionCreate


async def upload_questions(db: AsyncSession, source_id: int, questions: list[QuestionCreate]) -> list[Question]:
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    db_questions = []
    for q in questions:
        db_question = Question(
            source_id=source_id,
            question_text=q.question_text,
            choice_a=q.choice_a,
            choice_b=q.choice_b,
            choice_c=q.choice_c,
            choice_d=q.choice_d,
            choice_e=q.choice_e,
            answer=q.answer,
        )
        db.add(db_question)
        db_questions.append(db_question)
    
    source.question_count += len(db_questions)
    await db.commit()
    
    for q in db_questions:
        await db.refresh(q)
    
    return db_questions


async def list_questions(db: AsyncSession, source_id: int) -> list[Question]:
    result = await db.execute(
        select(Question).where(Question.source_id == source_id).order_by(Question.id)
    )
    return list(result.scalars().all())


async def update_solution(db: AsyncSession, question_id: int, solution: str) -> Question:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    question.solution = solution
    await db.commit()
    await db.refresh(question)
    return question


async def update_answer(db: AsyncSession, question_id: int, answer: int) -> Question:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    old_answer = question.answer
    question.answer = answer
    
    if old_answer is None and answer is not None:
        source = await db.get(Source, question.source_id)
        if source:
            source.answered_count += 1
    elif old_answer is not None and answer is None:
        source = await db.get(Source, question.source_id)
        if source and source.answered_count > 0:
            source.answered_count -= 1
    
    await db.commit()
    await db.refresh(question)
    return question


async def get_source_stats(db: AsyncSession, source_id: int) -> dict:
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return {
        "question_count": source.question_count,
        "answered_count": source.answered_count,
    }
