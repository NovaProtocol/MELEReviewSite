from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, TypeDecorator, func
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class FlexibleBlob(TypeDecorator):
    """LONGBLOB on MySQL, LargeBinary elsewhere."""
    impl = LargeBinary
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "mysql":
            return dialect.type_descriptor(LONGBLOB())
        return dialect.type_descriptor(LargeBinary())


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_blob: Mapped[bytes] = mapped_column(FlexibleBlob, nullable=False)
    pdf_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    date_created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    date_modified: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    questions: Mapped[list["Question"]] = relationship("Question", back_populates="source", lazy="selectin")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id"), index=True, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    choice_a: Mapped[str] = mapped_column(Text, nullable=False)
    choice_b: Mapped[str] = mapped_column(Text, nullable=False)
    choice_c: Mapped[str] = mapped_column(Text, nullable=False)
    choice_d: Mapped[str] = mapped_column(Text, nullable=False)
    choice_e: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    date_created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    date_modified: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    source: Mapped["Source"] = relationship("Source", back_populates="questions")
    solutions: Mapped[list["Solution"]] = relationship("Solution", back_populates="question")


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), index=True, nullable=False)
    convention: Mapped[str] = mapped_column(String(20), default="metric", nullable=False)
    blocks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    date_created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    date_modified: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="solutions")
