from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects.mysql import MEDIUMTEXT
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
    # NULL for the system administrator: its password lives in ADMIN_PASS and is
    # never written here, so a database leak cannot yield a usable administrator
    # credential at all.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissions: Mapped[int] = mapped_column(BigInt, default=0, nullable=False)
    # Progress is shown on the member page unless they turn it off. Stored as
    # "private" rather than "public" so the default row value is 0, which is what
    # a newly added boolean column backfills to.
    progress_private: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
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


class TopicPage(Base):
    """A topic's own prose: study material and a reference sheet.

    Two fixed kinds rather than a free-form page list, because the topic page has
    exactly two panels and a third would need a design decision, not a row.
    """

    __tablename__ = "topic_pages"
    __table_args__ = (UniqueConstraint("topic_id", "kind", name="uq_topic_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # resources | reference
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # A chapter of a transcribed book runs past MySQL's 64 KB TEXT ceiling.
    body: Mapped[str] = mapped_column(
        Text().with_variant(MEDIUMTEXT, "mysql"), default="", nullable=False
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


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
    # "computation" or "identification", asked for when the question is written.
    # Nullable only because rows written before the field existed have no value;
    # every read treats null as identification.
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
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
    # A solution used to be one photograph. The body is the Markdown that replaced
    # it; image_path stays for the rows written before that, which still render.
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    replies: Mapped[list[Reply]] = relationship(
        "Reply", back_populates="solution", cascade="all, delete-orphan"
    )


class Reply(Base):
    """A reply to a solution, and a reply to a reply.

    Threads hang off a solution: ``solution_id`` is the root of the thread and
    never changes, ``parent_id`` is the comment being answered. Keeping the root
    denormalised means a whole thread loads with one query instead of a walk.
    """

    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("solutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("replies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # "computation" or "identification", asked for when the question is written.
    # Nullable only because rows written before the field existed have no value;
    # every read treats null as identification.
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    solution: Mapped[Solution] = relationship("Solution", back_populates="replies")
    author: Mapped[User] = relationship("User", foreign_keys=[author_user_id])


class SolutionVote(Base):
    """One member's vote on one solution. Score is the sum across members."""

    __tablename__ = "solution_votes"
    __table_args__ = (UniqueConstraint("solution_id", "user_id", name="uq_solution_vote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("solutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vote: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ReplyVote(Base):
    """One member's vote on one reply."""

    __tablename__ = "reply_votes"
    __table_args__ = (UniqueConstraint("reply_id", "user_id", name="uq_reply_vote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reply_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("replies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vote: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Quiz(Base):
    """A saved paper.

    The code was the state before this; now the state is a row, so a quiz has an
    owner, a visibility, a life, and a submission history. The shareable address is
    `/quiz/<uid>`, which is short enough to say out loud.

    Deleting a quiz is permanent. Nothing about it is soft.
    """

    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON: timer_minutes, group, kind
    settings: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Unlisted: the link works, but only the owner and the administrator see it in
    # the list. A quiz idle for a week becomes private on its own.
    is_private: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False
    )
    scores_public: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )


class QuizQuestion(Base):
    """One slot in a paper.

    The id is kept even if the question is later retired, so the paper still shows
    what was asked and can be locked rather than silently changing.
    """

    __tablename__ = "quiz_questions"

    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class QuizSubmission(Base):
    """One sitting of a paper.

    One first take per member per quiz, kept forever and never overwritten. Later
    sittings are practice: they do not replace the score, and they are deleted six
    hours after their last update by the sweep.
    """

    __tablename__ = "quiz_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_first_take: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False, index=True
    )
    # JSON: {question_id: "A"}
    answers: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionReport(Base):
    """A member saying something is wrong with a question.

    A bad answer key is worse than no question, and only the people working the
    bank notice. One open report per member per question; resolving or dismissing
    it lets the same person raise it again if it comes back.
    """

    __tablename__ = "question_reports"
    __table_args__ = (
        UniqueConstraint("question_id", "reported_by_user_id", name="uq_report_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reported_by_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    # open | resolved | dismissed
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default=sa.text("'open'"), nullable=False, index=True
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Media(Base):
    """One uploaded image, and where it ended up.

    The file lives on the volume and the row is the record of it: who uploaded it,
    how big it is, its pixel size, and the question that currently references it.
    A question refers to an image by its uid (`/media/<uid>`), never by hostname,
    so the site can move to another domain without rewriting stored prose.
    """

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    solution_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("solutions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


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


class WorkspaceLayout(Base):
    """A member's workspace arrangement, saved so it follows them.

    The browser keeps its own copy because the first paint must not wait for a
    round trip. This is the copy that travels: on load the two timestamps are
    compared and the newer one wins, so a layout built on one machine opens on
    another, and a layout built offline is not lost by signing in elsewhere.
    """

    __tablename__ = "workspace_layouts"

    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    body: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=False)
    # When the arrangement was last edited, by the client's clock, in milliseconds.
    # Not the row's mtime: a restored layout is old even though it has just arrived.
    saved_at: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    date_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Formula(Base):
    """A formula you can put numbers into.

    Not a picture of an equation: an equation with named variables, their units and
    what each symbol means, so entering all but one answers the one. Kept in the
    database rather than a Python constant so a wrong unit can be fixed without a
    deploy.
    """

    __tablename__ = "formulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    section: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    equation: Mapped[str] = mapped_column(String(500), nullable=False)
    # {symbol: {label, unit, value?}} - the value is a default for a constant.
    variables: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    date_created: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class QuestionDraft(Base):
    """A member's private working for one question.

    The editor on a question page is where somebody works out an answer. Most of
    that working is private: a half-finished attempt, a sketch, a note to self.
    Publishing it is a separate act (ticking "mark as solution"), and a member can
    hold a private note and a published solution for the same question at once, so
    this is its own row rather than a flag on the solution.
    """

    __tablename__ = "question_drafts"
    __table_args__ = (UniqueConstraint("question_id", "user_id", name="uq_draft_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(
        Text().with_variant(MEDIUMTEXT, "mysql"), default="", nullable=False
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
    # Choices this member has crossed out while thinking. Letters, in order, so
    # "CD" means C and D are ruled out. Per member and per question, which is what
    # the flag row already is.
    struck: Mapped[str] = mapped_column(
        String(8), default="", server_default=sa.text("''"), nullable=False
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
