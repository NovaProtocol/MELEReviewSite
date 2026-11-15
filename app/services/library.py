"""Subjects, topics, and the public question read path.

Visibility is decided in one place: a question is public when it is not hidden
and its author is active. A ban therefore hides a user's whole history without
rewriting a single content row, and restoring the account brings it back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app import markdown, permissions
from app.config import get_config
from app.models import (
    Media,
    Question,
    QuestionAttempt,
    QuestionFlag,
    Solution,
    Subject,
    Topic,
    User,
)
from app.services import media_cleanup, metrics, taxonomy, threads

LETTERS = ("A", "B", "C", "D", "E")


def _public_question_filter():
    return (Question.is_hidden.is_(False), User.status == "active")


def _public_solution_filter():
    return (Solution.is_hidden.is_(False), User.status == "active")


async def list_subjects(db: AsyncSession) -> list[dict]:
    subject_rows = (
        (await db.execute(select(Subject).order_by(Subject.display_order, Subject.name)))
        .scalars()
        .all()
    )
    # Per-topic activity, so the library can be sorted by what is being used
    # rather than only by the taxonomy's own order.
    answers = (
        select(
            Question.topic_id.label("topic_id"),
            func.count(QuestionAttempt.id).label("answers"),
        )
        .join(QuestionAttempt, QuestionAttempt.question_id == Question.id)
        .group_by(Question.topic_id)
        .subquery()
    )
    topic_rows = (
        await db.execute(
            select(
                Topic,
                func.count(Question.id),
                func.coalesce(answers.c.answers, 0),
                func.max(Question.id),
            )
            .outerjoin(
                Question,
                (Question.topic_id == Topic.id)
                & Question.is_hidden.is_(False)
                & Question.is_deleted.is_(False),
            )
            .outerjoin(answers, answers.c.topic_id == Topic.id)
            .where(Topic.is_active.is_(True))
            .group_by(Topic.id, answers.c.answers)
            .order_by(Topic.display_order, Topic.name)
        )
    ).all()
    grouped: dict[int, list[dict]] = {}
    for topic, count, answered, newest in topic_rows:
        grouped.setdefault(topic.subject_id, []).append(
            {
                "id": topic.id,
                "name": topic.name,
                "questions": int(count),
                "answers": int(answered or 0),
                # The highest question id in the topic stands in for "newest",
                # which is monotonic and needs no second query.
                "newest": int(newest or 0),
                "is_active": topic.is_active,
            }
        )
    return [
        {
            "id": subject.id,
            "name": subject.name,
            "topics": grouped.get(subject.id, []),
        }
        for subject in subject_rows
    ]


async def get_topic(db: AsyncSession, topic_id: int) -> tuple[Topic, Subject]:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    subject = await db.get(Subject, topic.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return topic, subject


async def list_topics(db: AsyncSession, subject_id: int | None = None) -> list[Topic]:
    stmt = select(Topic).order_by(Topic.display_order, Topic.name)
    if subject_id is not None:
        stmt = stmt.where(Topic.subject_id == subject_id)
    return list((await db.execute(stmt)).scalars().all())


async def create_subject(db: AsyncSession, name: str) -> Subject:
    clean = name.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Name is required")
    exists = (await db.execute(select(Subject).where(Subject.name == clean))).scalars().first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="That subject already exists")
    highest = (await db.execute(select(func.max(Subject.display_order)))).scalar() or 0
    subject = Subject(name=clean, display_order=int(highest) + 1)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


async def rename_subject(db: AsyncSession, subject_id: int, name: str) -> Subject:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    clean = name.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Name is required")
    subject.name = clean
    await db.commit()
    await db.refresh(subject)
    return subject


async def create_topic(db: AsyncSession, subject_id: int, name: str) -> Topic:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    clean = name.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Name is required")
    clash = (
        (await db.execute(select(Topic).where(Topic.subject_id == subject_id, Topic.name == clean)))
        .scalars()
        .first()
    )
    if clash is not None:
        raise HTTPException(status_code=409, detail="That topic already exists")
    highest = (
        await db.execute(
            select(func.max(Topic.display_order)).where(Topic.subject_id == subject_id)
        )
    ).scalar() or 0
    topic = Topic(subject_id=subject_id, name=clean, display_order=int(highest) + 1)
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return topic


async def set_topic_active(db: AsyncSession, topic_id: int, is_active: bool) -> Topic:
    topic = await db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic.is_active = is_active
    await db.commit()
    await db.refresh(topic)
    return topic


async def has_solved(db: AsyncSession, question_id: int, user_id: int) -> bool:
    """Whether this member has answered the question correctly at least once."""
    row = (
        (
            await db.execute(
                select(QuestionAttempt.is_correct).where(
                    QuestionAttempt.question_id == question_id,
                    QuestionAttempt.user_id == user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    return bool(row)


async def _scores(db: AsyncSession, question_ids: list[int]) -> dict[int, int]:
    """Community score per question: the sum of every member's vote."""
    if not question_ids:
        return {}
    rows = await db.execute(
        select(QuestionFlag.question_id, func.coalesce(func.sum(QuestionFlag.vote), 0))
        .where(QuestionFlag.question_id.in_(question_ids))
        .group_by(QuestionFlag.question_id)
    )
    return {qid: int(score or 0) for qid, score in rows.all()}


async def _personal(db: AsyncSession, question_ids: list[int], viewer: User | None) -> dict:
    """This member's flags, so a list renders without a query per card."""
    if viewer is None or not question_ids:
        return {}
    rows = await db.execute(
        select(QuestionFlag).where(
            QuestionFlag.question_id.in_(question_ids), QuestionFlag.user_id == viewer.id
        )
    )
    return {flag.question_id: flag for flag in rows.scalars().all()}


async def may_see_solutions(db: AsyncSession, question_id: int, viewer: User | None) -> bool:
    """Reading someone's working is earned by answering, not by opening the page."""
    if viewer is None:
        return False
    if permissions.has(viewer.permissions, permissions.VIEW_HIDDEN):
        return True
    return await has_solved(db, question_id, viewer.id)


async def question_view(
    db: AsyncSession,
    question: Question,
    viewer: User | None = None,
    *,
    include_hidden: bool = False,
    with_solutions: bool = True,
    score: int | None = None,
    flag: QuestionFlag | None = None,
) -> dict:
    author = await db.get(User, question.author_user_id)
    solutions = []
    # Seeing someone else's working is earned by answering: not by opening the
    # page, and not by being wrong. The moderator and the admin keep their view.
    may_see = True
    if viewer is not None and not include_hidden:
        may_see = await may_see_solutions(db, question.id, viewer)
    elif viewer is None:
        may_see = False
    if with_solutions and may_see:
        solution_rows = (
            await db.execute(
                select(Solution, User.username, User.uid, User.status)
                .join(User, User.id == Solution.author_user_id)
                .where(Solution.question_id == question.id)
                .order_by(Solution.date_created)
            )
        ).all()
        for solution, username, uid, author_status in solution_rows:
            if solution.is_hidden and not include_hidden:
                continue
            if author_status != "active" and not include_hidden:
                continue
            solutions.append(
                {
                    "id": solution.id,
                    "image_url": f"/media/{solution.image_path}",
                    "note": solution.note,
                    "author": username,
                    "author_uid": uid,
                    "is_hidden": solution.is_hidden,
                    "body": solution.body,
                    "body_html": markdown.render(solution.body),
                    "date_created": solution.date_created,
                    "can_edit": bool(
                        viewer is not None
                        and (
                            solution.author_user_id == viewer.id
                            or permissions.has(viewer.permissions, permissions.MODERATE)
                        )
                    ),
                }
            )
        await threads.attach_threads(db, solutions, viewer)
    if with_solutions and may_see:
        solution_count = len(solutions)
    else:
        solution_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Solution)
                    .join(User, User.id == Solution.author_user_id)
                    .where(
                        Solution.question_id == question.id,
                        *([] if include_hidden else _public_solution_filter()),
                    )
                )
            ).scalar_one()
        )
    # The viewer's own solution, outside the gate: you may always see and edit
    # your own working, even before you have solved the question.
    my_solution = None
    if viewer is not None:
        mine = (
            (
                await db.execute(
                    select(Solution).where(
                        Solution.question_id == question.id,
                        Solution.author_user_id == viewer.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if mine is not None:
            my_solution = {
                "id": mine.id,
                # A solution written as a photograph opens in the editor as the
                # Markdown that now represents it, so editing starts from what is
                # already there instead of a blank box.
                "body": _editable_body(mine),
                "image_url": f"/media/{mine.image_path}" if mine.image_path else None,
                "note": mine.note,
            }

    attempt = None
    if viewer is not None:
        attempt_row = (
            (
                await db.execute(
                    select(QuestionAttempt).where(
                        QuestionAttempt.question_id == question.id,
                        QuestionAttempt.user_id == viewer.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if attempt_row is not None:
            attempt = {
                "chosen": attempt_row.chosen,
                "is_correct": attempt_row.is_correct,
                "solved": attempt_row.is_correct,
                # An attempt recorded before the attempt count existed reads as
                # zero. It still happened, so a solved row is at least one.
                "attempts": max(int(attempt_row.attempts or 0), 1),
                "first_correct": bool(attempt_row.first_correct),
            }
    if score is None:
        score = (await _scores(db, [question.id])).get(question.id, 0)
    return {
        "id": question.id,
        "topic_id": question.topic_id,
        "body": question.body,
        "body_html": markdown.render(question.body),
        "note_html": markdown.render(question.explanation),
        "choices": {
            "A": question.choice_a,
            "B": question.choice_b,
            "C": question.choice_c,
            "D": question.choice_d,
            "E": question.choice_e,
        },
        "correct_choice": question.correct_choice,
        "explanation": question.explanation,
        "is_hidden": question.is_hidden,
        "is_deleted": question.is_deleted,
        "tags": (await taxonomy.tags_for_questions(db, [question.id])).get(question.id, []),
        "author": author.username if author else None,
        "author_uid": author.uid if author else None,
        "author_avatar": f"/media/{author.avatar_path}" if author and author.avatar_path else None,
        "author_status": author.status if author else None,
        "solutions": solutions,
        "solution_count": solution_count,
        "may_see_solutions": may_see,
        "my_solution": my_solution,
        "attempt": attempt,
        "score": score,
        "vote": flag.vote if flag else 0,
        "is_favourite": bool(flag.is_favourite) if flag else False,
        "is_hidden_by_me": bool(flag.is_hidden) if flag else False,
        # The edit rule, resolved once here so the card does not re-derive it:
        # the author, or anyone holding MODERATE, nothing else.
        "can_edit": bool(
            viewer is not None
            and (
                question.author_user_id == viewer.id
                or permissions.has(viewer.permissions, permissions.MODERATE)
            )
        ),
        "date_created": question.date_created,
    }


async def list_questions(
    db: AsyncSession,
    topic_id: int,
    search: str = "",
    include_moderated_hidden: bool = False,
    include_personal_hidden: bool = False,
    viewer: User | None = None,
    favourites_only: bool = False,
    show_downvoted: bool = False,
    answer_state: str = "all",
    has_solution: bool = False,
    mine_only: bool = False,
    sort: str = "newest",
    per_page: int = 200,
) -> list[dict]:
    """The visible list for one topic.

    Two kinds of hidden, kept apart on purpose:

    - ``include_moderated_hidden`` is a moderator's view of what a moderator hid.
      It is separate so that a moderator's own eye button still works on their own
      list; holding VIEW_HIDDEN must not make the eye appear broken.
    - ``include_personal_hidden`` is the viewer's own "Show hidden" toggle.

    Plus ``show_downvoted`` for community-hidden questions and ``favourites_only``,
    which overrides the personal hide: a starred question you hid is still starred,
    and asking for your favourites is an explicit request to see them.

    The rest are independent: ``answer_state`` is the viewer's own sheet
    (answered/unanswered), ``has_solution`` asks whether anyone else posted
    working, and ``mine_only`` keeps the questions the viewer wrote. Any
    combination is valid, because a starred question can also be one you hid, and
    one you wrote, and one you have not answered.

    ``sort`` orders the list: newest, oldest, score (highest first), downvoted
    (lowest first), answered (most attempters first) or unsolved (fewest solvers).
    """
    stmt = (
        select(Question)
        .join(User, User.id == Question.author_user_id)
        .options(joinedload(Question.solutions))
        .where(Question.topic_id == topic_id)
    )
    if not include_moderated_hidden:
        stmt = stmt.where(Question.is_hidden.is_(False), User.status == "active")
    else:
        stmt = stmt.where(User.status == "active")
    if search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Question.body.like(term),
                Question.choice_a.like(term),
                Question.choice_b.like(term),
                Question.choice_c.like(term),
                Question.choice_d.like(term),
            )
        )

    scores = (
        select(
            QuestionFlag.question_id.label("question_id"),
            func.sum(QuestionFlag.vote).label("score"),
        )
        .group_by(QuestionFlag.question_id)
        .subquery()
    )

    if viewer is not None:
        if mine_only:
            stmt = stmt.where(Question.author_user_id == viewer.id)
        if answer_state in {"answered", "unanswered"}:
            mine = (
                select(QuestionAttempt.question_id)
                .where(QuestionAttempt.user_id == viewer.id)
                .subquery()
            )
            stmt = stmt.outerjoin(mine, mine.c.question_id == Question.id)
            if answer_state == "answered":
                stmt = stmt.where(mine.c.question_id.is_not(None))
            else:
                stmt = stmt.where(mine.c.question_id.is_(None))
        stmt = stmt.outerjoin(
            QuestionFlag,
            (QuestionFlag.question_id == Question.id) & (QuestionFlag.user_id == viewer.id),
        )
        if favourites_only:
            stmt = stmt.where(QuestionFlag.is_favourite.is_(True))
        elif not include_personal_hidden:
            stmt = stmt.where(
                or_(QuestionFlag.is_hidden.is_(None), QuestionFlag.is_hidden.is_(False))
            )

    if has_solution:
        answered_questions = (
            select(Solution.question_id)
            .join(User, User.id == Solution.author_user_id)
            .where(*_public_solution_filter())
            .distinct()
            .subquery()
        )
        stmt = stmt.where(Question.id.in_(select(answered_questions.c.question_id)))

    stmt = stmt.outerjoin(scores, scores.c.question_id == Question.id)
    negative = func.coalesce(scores.c.score, 0) < 0
    if not show_downvoted:
        stmt = stmt.where(~negative)

    # Only join the activity aggregate when the order actually needs it.
    activity = None
    if sort in {"answered", "unsolved"}:
        activity = (
            select(
                QuestionAttempt.question_id.label("question_id"),
                func.count(QuestionAttempt.id).label("attempters"),
                func.sum(cast(QuestionAttempt.is_correct, Integer)).label("solvers"),
            )
            .group_by(QuestionAttempt.question_id)
            .subquery()
        )
        stmt = stmt.outerjoin(activity, activity.c.question_id == Question.id)

    orders = {
        "newest": Question.id.desc(),
        "oldest": Question.id.asc(),
        "score": func.coalesce(scores.c.score, 0).desc(),
        "downvoted": func.coalesce(scores.c.score, 0).asc(),
    }
    if activity is not None:
        orders["answered"] = func.coalesce(activity.c.attempters, 0).desc()
        orders["unsolved"] = func.coalesce(activity.c.solvers, 0).asc()
    stmt = stmt.order_by(orders.get(sort, Question.id.desc()))

    rows = (await db.execute(stmt.limit(per_page))).scalars().unique().all()
    ids = [q.id for q in rows]
    score_map = await _scores(db, ids)
    flag_map = await _personal(db, ids, viewer)
    return [
        await question_view(
            db,
            q,
            viewer,
            include_hidden=include_moderated_hidden,
            with_solutions=False,
            score=score_map.get(q.id, 0),
            flag=flag_map.get(q.id),
        )
        for q in rows
    ]


async def set_favourite(db: AsyncSession, question: Question, user: User) -> dict:
    flag = await _flag_row(db, question.id, user.id)
    flag.is_favourite = not flag.is_favourite
    await db.commit()
    return await _flag_state(db, question.id, flag)


async def set_personal_hidden(db: AsyncSession, question: Question, user: User) -> dict:
    """Hide a question for this member only. Favourite and hide are independent."""
    flag = await _flag_row(db, question.id, user.id)
    flag.is_hidden = not flag.is_hidden
    await db.commit()
    return await _flag_state(db, question.id, flag)


async def set_vote(db: AsyncSession, question: Question, user: User, direction: int) -> dict:
    """Apply an up or down vote; voting the same way twice clears the vote."""
    if direction not in (-1, 0, 1):
        raise HTTPException(status_code=422, detail="Vote must be -1, 0 or 1")
    flag = await _flag_row(db, question.id, user.id)
    flag.vote = 0 if flag.vote == direction else direction
    await db.commit()
    return await _flag_state(db, question.id, flag)


async def _flag_row(db: AsyncSession, question_id: int, user_id: int) -> QuestionFlag:
    row = (
        (
            await db.execute(
                select(QuestionFlag).where(
                    QuestionFlag.question_id == question_id, QuestionFlag.user_id == user_id
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = QuestionFlag(question_id=question_id, user_id=user_id)
        db.add(row)
        await db.flush()
    return row


async def _flag_state(db: AsyncSession, question_id: int, flag: QuestionFlag) -> dict:
    score = (await _scores(db, [question_id])).get(question_id, 0)
    return {
        "question_id": question_id,
        "vote": flag.vote,
        "score": score,
        "is_favourite": bool(flag.is_favourite),
        "is_hidden_by_me": bool(flag.is_hidden),
    }


async def get_question(db: AsyncSession, question_id: int) -> Question:
    question = await db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


async def _other_reference(
    db: AsyncSession,
    uid: str,
    *,
    question_id: int | None = None,
    solution_id: int | None = None,
) -> tuple[str, int] | None:
    """Something else that still shows this upload, and what kind of thing."""
    pattern = f"%{uid}%"
    query = select(Question.id).where(
        or_(Question.body.like(pattern), Question.explanation.like(pattern))
    )
    if question_id is not None:
        query = query.where(Question.id != question_id)
    found = (await db.execute(query.limit(1))).scalars().first()
    if found is not None:
        return ("question", found)

    query = select(Solution.id).where(Solution.body.like(pattern))
    if solution_id is not None:
        query = query.where(Solution.id != solution_id)
    found = (await db.execute(query.limit(1))).scalars().first()
    if found is not None:
        return ("solution", found)
    return None


def _hand_over(row: Media, owner: tuple[str, int]) -> None:
    """Point the row at whatever still references it, keeping one owner."""
    kind, owner_id = owner
    if kind == "question":
        row.question_id = owner_id
        row.solution_id = None
    else:
        row.solution_id = owner_id
        row.question_id = None


async def _link_media(db: AsyncSession, question: Question) -> list[str]:
    """Record which question uses each uploaded image, and drop what it dropped.

    The prose is the source of truth: whatever it references is claimed, and an
    image the edit removed is deleted outright rather than left on disk. The
    returned paths are removed from the volume by the caller after the commit, so
    a failed save cannot leave a row pointing at a file that is already gone.
    """
    referenced = markdown.extract_media_uids(question.body) + markdown.extract_media_uids(
        question.explanation
    )
    released: list[str] = []
    rows = (await db.execute(select(Media).where(Media.question_id == question.id))).scalars().all()
    for row in rows:
        if row.uid in referenced:
            continue
        # The same upload can be pasted into another question, and the row can only
        # point at one owner. Hand it over rather than delete a file that is still
        # on somebody's page.
        other = await _other_reference(db, row.uid, question_id=question.id)
        if other is not None:
            _hand_over(row, other)
            continue
        released.append(row.path)
        await db.delete(row)
    if referenced:
        claimed = (await db.execute(select(Media).where(Media.uid.in_(referenced)))).scalars().all()
        for row in claimed:
            row.question_id = question.id
            row.solution_id = None
    return released


def _editable_body(solution: Solution) -> str:
    """The Markdown an editor should open with, legacy rows included."""
    if solution.body:
        return solution.body
    parts = []
    if solution.image_path:
        parts.append(f"![]({f'/media/{solution.image_path}'})")
    if solution.note:
        parts.append(solution.note)
    return "\n\n".join(parts)


async def _link_solution_media(db: AsyncSession, solution: Solution) -> list[str]:
    """Record the images a solution's Markdown uses, and drop what it dropped."""
    referenced = markdown.extract_media_uids(solution.body)
    released: list[str] = []
    rows = (await db.execute(select(Media).where(Media.solution_id == solution.id))).scalars().all()
    for row in rows:
        if row.uid in referenced:
            continue
        other = await _other_reference(db, row.uid, solution_id=solution.id)
        if other is not None:
            _hand_over(row, other)
            continue
        released.append(row.path)
        await db.delete(row)
    if referenced:
        claimed = (await db.execute(select(Media).where(Media.uid.in_(referenced)))).scalars().all()
        for row in claimed:
            row.solution_id = solution.id
            row.question_id = None
    return released


def _solution_body(body: str | None) -> str:
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="A solution needs something in it")
    if len(text) > 20000:
        raise HTTPException(status_code=422, detail="That solution is too long")
    return text


async def save_solution(db: AsyncSession, question: Question, author: User, body: str) -> Solution:
    """Create or replace this member's solution to one question."""
    permissions.require(author.permissions, permissions.ANSWER_QUESTION)
    text = _solution_body(body)
    existing = (
        (
            await db.execute(
                select(Solution).where(
                    Solution.question_id == question.id,
                    Solution.author_user_id == author.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        solution = Solution(
            question_id=question.id,
            author_user_id=author.id,
            body=text,
            image_path=None,
        )
        db.add(solution)
        await db.flush()
    else:
        solution = existing
        solution.body = text
        # A legacy photograph is replaced by the prose that supersedes it.
        solution.image_path = None
        solution.is_hidden = False
        solution.hidden_by_user_id = None
        solution.hidden_at = None
        await db.flush()
    released = await _link_solution_media(db, solution)
    await db.commit()
    await media_cleanup.remove_paths(get_config().upload_dir, released)
    await db.refresh(solution)
    return solution


async def edit_solution(db: AsyncSession, solution: Solution, actor: User, body: str) -> Solution:
    """Edit a solution: its author, or a moderator acting for the site."""
    if solution.author_user_id != actor.id and not permissions.has(
        actor.permissions, permissions.MODERATE
    ):
        raise HTTPException(status_code=403, detail="Not your solution")
    solution.body = _solution_body(body)
    solution.image_path = None
    await db.flush()
    released = await _link_solution_media(db, solution)
    await db.commit()
    await media_cleanup.remove_paths(get_config().upload_dir, released)
    await db.refresh(solution)
    return solution


async def remove_solution(db: AsyncSession, solution: Solution, actor: User) -> None:
    """Delete a solution along with any image only it was using."""
    if solution.author_user_id != actor.id and not permissions.has(
        actor.permissions, permissions.MODERATE
    ):
        raise HTTPException(status_code=403, detail="Not your solution")
    rows = (await db.execute(select(Media).where(Media.solution_id == solution.id))).scalars().all()
    released: list[str] = []
    for row in rows:
        other = await _other_reference(db, row.uid, solution_id=solution.id)
        if other is not None:
            _hand_over(row, other)
            continue
        released.append(row.path)
        await db.delete(row)
    if solution.image_path:
        released.append(solution.image_path)
    await db.delete(solution)
    await db.commit()
    await media_cleanup.remove_paths(get_config().upload_dir, released)


async def create_question(db: AsyncSession, author: User, data: dict) -> Question:
    permissions.require(author.permissions, permissions.POST_QUESTION)
    topic = await db.get(Topic, int(data["topic_id"]))
    if topic is None or not topic.is_active:
        raise HTTPException(status_code=400, detail="Choose an active topic")
    correct = str(data.get("correct_choice", "")).strip().upper()
    if correct not in LETTERS:
        raise HTTPException(status_code=422, detail="Correct choice must be A to E")
    question = Question(
        topic_id=topic.id,
        author_user_id=author.id,
        body=str(data["body"]).strip(),
        choice_a=str(data["choice_a"]).strip(),
        choice_b=str(data["choice_b"]).strip(),
        choice_c=str(data["choice_c"]).strip(),
        choice_d=str(data["choice_d"]).strip(),
        choice_e=(str(data["choice_e"]).strip() or None) if data.get("choice_e") else None,
        correct_choice=correct,
        explanation=(str(data["explanation"]).strip() or None) if data.get("explanation") else None,
    )
    if not question.body:
        raise HTTPException(status_code=422, detail="The question text is required")
    db.add(question)
    # Flush first: the count must include the row being created.
    await db.flush()
    await taxonomy.set_question_tags(db, question.id, data.get("tags") or [])
    await _link_media(db, question)
    await metrics.refresh_user(db, author.id)
    await db.commit()
    await db.refresh(question)
    return question


async def update_question(
    db: AsyncSession, question: Question, actor: User, data: dict
) -> Question:
    owns = question.author_user_id == actor.id
    if not owns and not permissions.has(actor.permissions, permissions.MODERATE):
        raise HTTPException(status_code=403, detail="Not your question")
    correct = str(data.get("correct_choice", question.correct_choice)).strip().upper()
    if correct not in LETTERS:
        raise HTTPException(status_code=422, detail="Correct choice must be A to E")
    question.body = str(data.get("body", question.body)).strip()
    for letter in LETTERS[:4]:
        key = f"choice_{letter.lower()}"
        if key in data:
            setattr(question, key, str(data[key]).strip())
    if "choice_e" in data:
        value = str(data["choice_e"] or "").strip()
        question.choice_e = value or None
    if "explanation" in data:
        value = str(data["explanation"] or "").strip()
        question.explanation = value or None
    question.correct_choice = correct
    await db.flush()
    if "tags" in data:
        await taxonomy.set_question_tags(db, question.id, data.get("tags") or [])
    released = await _link_media(db, question)
    # An edit makes every attempt on it a measurement of a different problem, so
    # the attempt rows go. The author keeps the "question written" count: they did
    # write it, and the row still exists.
    cleared = await metrics.clear_attempts_for_question(db, question.id)
    await metrics.refresh_many(db, [*cleared, question.author_user_id])
    await db.commit()
    await media_cleanup.remove_paths(get_config().upload_dir, released)
    await db.refresh(question)
    return question


async def hide_question(
    db: AsyncSession, question: Question, actor: User, hidden: bool
) -> Question:
    """Hide or restore a question for everyone.

    Hiding is not deleting: the row and every attempt on it stay, so restoring it
    brings back a question people had already answered. Only an edit resets
    attempts, because only an edit changes the problem.
    """
    permissions.require(actor.permissions, permissions.MODERATE)
    question.is_hidden = hidden
    question.hidden_by_user_id = actor.id if hidden else None
    question.hidden_at = None
    if hidden:
        question.hidden_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(question)
    return question


async def record_attempt(db: AsyncSession, question: Question, user: User, chosen: str) -> dict:
    """Record one try, keeping a single row per member per question.

    ``first_selection`` is written once and never moved, because the first-try
    rate is a different question from "did they get there eventually". A right
    answer locks the sheet: further selections are refused rather than counted,
    so the attempt count measures tries, not clicks.
    """
    letter = chosen.strip().upper()
    if letter not in LETTERS:
        raise HTTPException(status_code=422, detail="Choose A to E")

    existing = (
        (
            await db.execute(
                select(QuestionAttempt).where(
                    QuestionAttempt.question_id == question.id,
                    QuestionAttempt.user_id == user.id,
                )
            )
        )
        .scalars()
        .first()
    )

    if existing is not None and existing.is_correct:
        raise HTTPException(status_code=409, detail="You already answered this correctly")

    is_correct = letter == question.correct_choice
    if existing is None:
        attempt = QuestionAttempt(
            question_id=question.id,
            user_id=user.id,
            chosen=letter,
            first_selection=letter,
            first_correct=is_correct,
            is_correct=is_correct,
            attempts=1,
        )
        db.add(attempt)
        attempts = 1
    else:
        existing.chosen = letter
        existing.is_correct = existing.is_correct or is_correct
        # max(..., 1) counts a legacy row as the one try it already represents,
        # so an old answer is not silently worth zero.
        existing.attempts = max(int(existing.attempts or 0), 1) + 1
        attempts = existing.attempts

    await db.flush()
    await metrics.refresh_user(db, user.id)
    await db.commit()

    return {
        "chosen": letter,
        "is_correct": is_correct,
        "solved": bool(existing.is_correct) if existing is not None else is_correct,
        "attempts": attempts,
        # Deliberately absent until solved: a wrong answer must not reveal the
        # right one, or the second try is not a try.
        "correct_choice": question.correct_choice if is_correct else None,
    }


async def progress_for(db: AsyncSession, user: User) -> dict:
    """The member's numbers, read from the cached counters on their row.

    The counters are maintained by ``app.services.metrics``; reading them here
    keeps a profile page to one query instead of an aggregate over every attempt.
    """
    favourites = int(
        (
            await db.execute(
                select(func.count())
                .select_from(QuestionFlag)
                .where(QuestionFlag.user_id == user.id, QuestionFlag.is_favourite.is_(True))
            )
        ).scalar_one()
    )
    return {
        "questions": user.metric_questions,
        "answered": user.metric_answered,
        "first_correct": user.metric_first_correct,
        "solved": user.metric_solved,
        "first_try_rate": user.first_try_rate,
        "overall_rate": user.overall_rate,
        "average_tries": user.average_tries,
        "favourites": favourites,
    }


async def hidden_content(db: AsyncSession) -> dict:
    """Everything the public site is not showing, for the administrator."""
    hidden_questions = (
        await db.execute(
            select(Question, User.username, Topic.name, Subject.name)
            .join(User, User.id == Question.author_user_id)
            .join(Topic, Topic.id == Question.topic_id)
            .join(Subject, Subject.id == Topic.subject_id)
            .where(Question.is_hidden.is_(True))
            .order_by(Question.id.desc())
        )
    ).all()
    hidden_solutions = (
        await db.execute(
            select(Solution, User.username, Question.body)
            .join(User, User.id == Solution.author_user_id)
            .join(Question, Question.id == Solution.question_id)
            .where(Solution.is_hidden.is_(True))
            .order_by(Solution.id.desc())
        )
    ).all()
    return {
        "questions": [
            {
                "id": q.id,
                "body": q.body,
                "topic": topic,
                "subject": subject,
                "author": username,
                "hidden_at": q.hidden_at,
            }
            for q, username, topic, subject in hidden_questions
        ],
        "solutions": [
            {
                "id": s.id,
                "question_id": s.question_id,
                "question": body[:160],
                "author": username,
                "hidden_at": s.hidden_at,
            }
            for s, username, body in hidden_solutions
        ],
    }


async def recently_answered(db: AsyncSession, user: User, limit: int = 6) -> list[dict]:
    """Questions this member attempted, most recent first.

    Deliberately carries no answer: the card shows where they left off, not the
    solution. A question they never solved appears here too, which is the point.
    On another member's page this is their history, which is public to signed-in
    members; the attempt counts are already on the profile.
    """
    rows = await db.execute(
        select(QuestionAttempt, Question, Topic.name, Subject.name)
        .join(Question, Question.id == QuestionAttempt.question_id)
        .join(Topic, Topic.id == Question.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .where(
            QuestionAttempt.user_id == user.id,
            Question.is_deleted.is_(False),
            Question.is_hidden.is_(False),
        )
        .order_by(QuestionAttempt.date_modified.desc())
        .limit(limit)
    )
    out = []
    for attempt, question, topic_name, subject_name in rows.all():
        out.append(
            {
                "id": question.id,
                "topic_id": question.topic_id,
                "body": question.body,
                "topic": topic_name,
                "subject": subject_name,
                "attempts": max(int(attempt.attempts or 0), 1),
                "solved": bool(attempt.is_correct),
            }
        )
    return out


async def newest_questions(
    db: AsyncSession, user: User, limit: int = 6, author_id: int | None = None
) -> list[dict]:
    """The latest questions, optionally only those one member wrote."""
    conditions = [
        Question.is_deleted.is_(False),
        Question.is_hidden.is_(False),
        User.status == "active",
    ]
    if author_id is not None:
        conditions.append(Question.author_user_id == author_id)
    rows = await db.execute(
        select(Question, Topic.name, Subject.name, User.username)
        .join(Topic, Topic.id == Question.topic_id)
        .join(Subject, Subject.id == Topic.subject_id)
        .join(User, User.id == Question.author_user_id)
        .where(*conditions)
        .order_by(Question.id.desc())
        .limit(limit)
    )
    return [
        {
            "id": question.id,
            "topic_id": question.topic_id,
            "body": question.body,
            "topic": topic_name,
            "subject": subject_name,
            "author": author,
        }
        for question, topic_name, subject_name, author in rows.all()
    ]
