from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


question_tags = Table(
    "question_tags",
    Base.metadata,
    Column("question_id", Integer, ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    pin: Mapped[str] = mapped_column(String(100), nullable=False)
    date_created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    solutions: Mapped[list["Solution"]] = relationship(
        "Solution", back_populates="account", cascade="all, delete-orphan"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    choice_a: Mapped[str] = mapped_column(Text, nullable=False)
    choice_b: Mapped[str] = mapped_column(Text, nullable=False)
    choice_c: Mapped[str] = mapped_column(Text, nullable=False)
    choice_d: Mapped[str] = mapped_column(Text, nullable=False)
    choice_e: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    date_created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    date_modified: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    tags: Mapped[list[Tag]] = relationship("Tag", secondary=question_tags, lazy="selectin")
    solutions: Mapped[list["Solution"]] = relationship(
        "Solution",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    convention: Mapped[str] = mapped_column(String(20), default="metric", nullable=False)
    blocks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    date_created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    date_modified: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    question: Mapped[Question] = relationship("Question", back_populates="solutions")
    account: Mapped[Account] = relationship("Account", back_populates="solutions")
