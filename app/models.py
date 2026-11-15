from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# MySQL wants BIGINT for a user id; SQLite only autoincrements an INTEGER
# PRIMARY KEY. One type, two dialects, so the models stay portable.
BigInt = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    # Immutable public identifier. It is what other rows and links carry, so a
    # username change never breaks a reference.
    uid: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissions: Mapped[int] = mapped_column(BigInt, default=0, nullable=False)
    is_system_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    # active | banned | revoked
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default=sa.text("'active'"), nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status_root_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invited_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Denormalised so a profile renders without scanning the attempt table.
    # Every value is recomputed from question_attempts after any change that can
    # move it; see app/services/metrics.py. Never write these by hand.
    metric_questions: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    metric_answered: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    metric_first_correct: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    metric_solved: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    # Sum of min(attempts, 4) over answered questions, so the average is capped.
    metric_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    date_last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    date_modified: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    inviter: Mapped[User | None] = relationship(
        "User", remote_side=[id], foreign_keys=[invited_by_user_id]
    )
    status_root: Mapped[User | None] = relationship(
        "User", remote_side=[id], foreign_keys=[status_root_user_id]
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def first_try_rate(self) -> float:
        if not self.metric_answered:
            return 0.0
        return round(self.metric_first_correct / self.metric_answered * 100, 1)

    @property
    def overall_rate(self) -> float:
        if not self.metric_answered:
            return 0.0
        return round(self.metric_solved / self.metric_answered * 100, 1)

    @property
    def average_tries(self) -> float:
        if not self.metric_answered:
            return 0.0
        return round(self.metric_attempts / self.metric_answered, 1)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    used_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    creator: Mapped[User] = relationship("User", foreign_keys=[created_by_user_id])
    used_by: Mapped[User | None] = relationship("User", foreign_keys=[used_by_user_id])

    @property
    def is_open(self) -> bool:
        return self.used_by_user_id is None and self.revoked_at is None


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    topics: Mapped[list[Topic]] = relationship(
        "Topic", back_populates="subject", order_by="Topic.display_order"
    )


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("subject_id", "name", name="uq_topic_subject_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    subject: Mapped[Subject] = relationship("Subject", back_populates="topics")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    choice_a: Mapped[str] = mapped_column(Text, nullable=False)
    choice_b: Mapped[str] = mapped_column(Text, nullable=False)
    choice_c: Mapped[str] = mapped_column(Text, nullable=False)
    choice_d: Mapped[str] = mapped_column(Text, nullable=False)
    choice_e: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_choice: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    hidden_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Deleted is a stronger state than hidden: hidden keeps the question (and its
    # attempts) as part of the record, deleted removes it from the metrics too.
    # Neither removes the row, so the administrator can still see and restore it.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    deleted_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    date_modified: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    topic: Mapped[Topic] = relationship("Topic")
    author: Mapped[User] = relationship("User", foreign_keys=[author_user_id])
    solutions: Mapped[list[Solution]] = relationship(
        "Solution", back_populates="question", cascade="all, delete-orphan"
    )


class Solution(Base):
    __tablename__ = "solutions"
    __table_args__ = (UniqueConstraint("question_id", "author_user_id", name="uq_solution_author"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    hidden_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    question: Mapped[Question] = relationship("Question", back_populates="solutions")
    author: Mapped[User] = relationship("User", foreign_keys=[author_user_id])


class QuestionAttempt(Base):
    """One member's answer sheet for one question.

    Exactly one row per (member, question), however many times they tried. The row
    is deleted outright when the question's content changes, because a retry
    against a different problem is not the same measurement.

    ``chosen`` is the most recent selection and ``is_correct`` is "solved": true
    once they have picked the right one. ``first_selection`` is kept because the
    first-try rate is a different number from the eventual one.
    """

    __tablename__ = "question_attempts"
    __table_args__ = (UniqueConstraint("question_id", "user_id", name="uq_attempt_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chosen: Mapped[str] = mapped_column(String(1), nullable=False)
    first_selection: Mapped[str | None] = mapped_column(String(1), nullable=True)
    is_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    first_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    date_modified: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class QuestionFlag(Base):
    """One member's standing on one question.

    Favourite and personal-hide are separate booleans, so a question can be both:
    saved for later and quietly out of the list. The vote is +1, -1 or 0, and the
    display score is the sum across members.
    """

    __tablename__ = "question_flags"
    __table_args__ = (UniqueConstraint("question_id", "user_id", name="uq_flag_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_favourite: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    vote: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Tag(Base):
    """A free-form label that cuts across the taxonomy.

    Topics are a tree (a question lives in exactly one), tags are a web: a
    question about a derivative can sit under kinematics and carry `derivative`
    alongside questions from calculus. Names are stored lowercased and unique
    case-insensitively by normalising on write.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


question_tags = Table(
    "question_tags",
    Base.metadata,
    Column(
        "question_id",
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_question_tags_tag", "tag_id"),
)


Index("ix_questions_topic_hidden", Question.topic_id, Question.is_hidden)
Index("ix_questions_deleted", Question.is_deleted)
