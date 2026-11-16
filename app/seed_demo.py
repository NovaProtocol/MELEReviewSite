"""Reset the demo content: empty the bank, then write a seeded one.

Run inside the app container:

    python -m app.seed_demo

It deletes every question, answer, solution, report and member below the system
administrator, then writes a fresh bank: 100 questions in algebra and 10 in every
other topic. The questions are generated, not quoted, and carry Markdown and
formulas so the editor's features are visible in the seeded content.

The administrator and the subjects and topics are kept. Everything else goes.
"""

from __future__ import annotations

import asyncio
import random
import re

from sqlalchemy import delete, select

from app.db import _get_session_factory
from app.models import (
    Invite,
    Media,
    Question,
    QuestionAttempt,
    QuestionFlag,
    QuestionReport,
    Reply,
    ReplyVote,
    Solution,
    SolutionVote,
    Subject,
    Tag,
    Topic,
    User,
    question_tags,
)
from app.services import metrics

ALGEBRA_QUESTIONS = 100
OTHER_QUESTIONS = 10
SEED = 20261116

# Wipe order: children before parents, because the foreign keys say so.
WIPE = (
    ReplyVote,
    SolutionVote,
    Reply,
    Solution,
    QuestionReport,
    QuestionAttempt,
    QuestionFlag,
    Media,
)

COMPUTATION = [
    (
        "In **{topic}**, a quantity follows\n\n$$y = {a}x^{{2}} + {b}x + {c}$$\n\n"
        "Find $y$ when $x = {x}$.",
        lambda a, b, c, x: a * x * x + b * x + c,
        "y",
    ),
    (
        "A **{topic}** problem gives $P = {a}\\,\\mathrm{{kW}}$ over $t = {b}\\,\\mathrm{{s}}$.\n\n"
        "What is the energy transferred, in kJ?",
        lambda a, b, c, x: a * b,
        "E",
    ),
    (
        "In **{topic}**, the efficiency of a cycle is\n\n"
        "$$\\eta = \\frac{{W_{{\\mathrm{{out}}}}}}{{Q_{{\\mathrm{{in}}}}}}\\times 100\\%$$\n\n"
        "with $W_{{\\mathrm{{out}}}} = {a}\\,\\mathrm{{kJ}}$ and "
        "$Q_{{\\mathrm{{in}}}} = {b}\\,\\mathrm{{kJ}}$. Find $\\eta$.",
        lambda a, b, c, x: round(100 * a / b, 1),
        "%",
    ),
    (
        "The relation in **{topic}** is\n\n"
        "$$\\frac{{1}}{{R_{{\\mathrm{{eq}}}}}} = \\frac{{1}}{{{a}}} + \\frac{{1}}{{{b}}}$$\n\n"
        "Find $R_{{\\mathrm{{eq}}}}$, in the same units.",
        lambda a, b, c, x: round(1 / (1 / a + 1 / b), 2),
        "",
    ),
    (
        "In **{topic}**, a reading scales with the square root of the head:\n\n"
        "$$v = \\sqrt{{2gh}}$$\n\n"
        "Take $g = 9.81\\,\\mathrm{{m/s^2}}$ and $h = {a}\\,\\mathrm{{m}}$. Find $v$.",
        lambda a, b, c, x: round((2 * 9.81 * a) ** 0.5, 2),
        "m/s",
    ),
]

IDENTIFICATION = [
    (
        "In **{topic}**, which term names the quantity defined as the rate of doing work?",
        "Power",
        ["Work", "Energy", "Momentum"],
    ),
    (
        "Which statement is the **{topic}** principle of conservation of energy?",
        "Energy is neither created nor destroyed, only converted",
        [
            "Energy always increases in a closed system",
            "Heat always flows from cold to hot",
            "Mass is converted to force at constant pressure",
        ],
    ),
    (
        "In **{topic}**, the ratio of useful output to input is called the",
        "Efficiency",
        ["Load factor", "Duty cycle", "Specific speed"],
    ),
    (
        "Which of these is a **{topic}** intensive property?",
        "Temperature",
        ["Mass", "Volume", "Total enthalpy"],
    ),
]


def _words(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _numbers(rng: random.Random) -> tuple[int, int, int, int]:
    a = rng.randint(2, 40)
    b = rng.randint(2, 25)
    c = rng.randint(1, 15)
    x = rng.randint(2, 12)
    return a, b, c, x


def _computation(rng: random.Random, topic: str) -> tuple[str, list[str], str, str]:
    which = rng.randrange(len(COMPUTATION))
    template, solver, unit = COMPUTATION[which]
    a, b, c, x = _numbers(rng)
    if which == 2:
        # Efficiency is work out over heat in; an answer above 100% would be a
        # question that teaches the wrong thing.
        a, b = sorted((a, b))
    body = template.format(topic=topic, a=a, b=b, c=c, x=x)
    answer = solver(a, b, c, x)
    correct = f"{answer} {unit}".strip()

    spread = max(abs(float(answer)) * 0.12, 1.0)
    wrong = []
    while len(wrong) < 3:
        offset = round(rng.uniform(0.4, 1.4) * spread, 2)
        candidate = round(answer + rng.choice((-1, 1)) * offset, 2)
        if candidate != answer and f"{candidate} {unit}".strip() not in wrong:
            wrong.append(f"{candidate} {unit}".strip())
    return body, [correct, *wrong], correct, ""


def _identification(rng: random.Random, topic: str) -> tuple[str, list[str], str, str]:
    body, correct, others = rng.choice(IDENTIFICATION)
    return body.format(topic=topic), [correct, *others], correct, ""


def _make(rng: random.Random, topic: str, index: int) -> dict:
    # Four in five are computations: an MELE bank is mostly worked problems, and
    # the quiz's "leave out computations" filter needs both to exist.
    if index % 5 == 4:
        body, choices, correct, _unit = _identification(rng, topic)
        kind = "identification"
    else:
        body, choices, correct, _unit = _computation(rng, topic)
        kind = "computation"
    rng.shuffle(choices)
    letter = "ABCD"[choices.index(correct)]
    return {
        "body": body,
        "choices": choices,
        "correct": letter,
        "kind": kind,
    }


async def clear(factory) -> tuple[dict, int | None]:
    removed = {}
    async with factory() as db:
        for model in WIPE:
            result = await db.execute(delete(model))
            removed[model.__tablename__] = result.rowcount or 0
        await db.execute(delete(question_tags))
        await db.execute(delete(Tag))
        await db.execute(delete(Question))
        await db.execute(delete(Invite))
        admin = (
            (await db.execute(select(User).where(User.is_system_admin.is_(True)))).scalars().first()
        )
        if admin is not None:
            result = await db.execute(delete(User).where(User.id != admin.id))
            removed["users"] = result.rowcount or 0
        await db.commit()
        return removed, admin.id if admin else None


async def seed(factory, author_id: int) -> dict:
    rng = random.Random(SEED)
    written = {}
    async with factory() as db:
        subjects = (
            (await db.execute(select(Subject).order_by(Subject.display_order, Subject.name)))
            .scalars()
            .all()
        )
        for subject in subjects:
            topics = (
                (
                    await db.execute(
                        select(Topic)
                        .where(Topic.subject_id == subject.id)
                        .order_by(Topic.display_order, Topic.name)
                    )
                )
                .scalars()
                .all()
            )
            for topic in topics:
                algebra = topic.name.strip().lower() == "algebra"
                count = ALGEBRA_QUESTIONS if algebra else OTHER_QUESTIONS
                tag_name = _words(topic.name)[:40] or "topic"
                tag = (await db.execute(select(Tag).where(Tag.name == tag_name))).scalars().first()
                if tag is None:
                    tag = Tag(name=tag_name)
                    db.add(tag)
                    await db.flush()
                for index in range(count):
                    built = _make(rng, topic.name, index)
                    question = Question(
                        topic_id=topic.id,
                        author_user_id=author_id,
                        body=built["body"],
                        choice_a=built["choices"][0],
                        choice_b=built["choices"][1],
                        choice_c=built["choices"][2],
                        choice_d=built["choices"][3],
                        correct_choice=built["correct"],
                        kind=built["kind"],
                        explanation=(
                            "Use $g = 9.81\\,\\mathrm{m/s^2}$ unless the problem says otherwise."
                            if index % 3 == 0
                            else None
                        ),
                    )
                    db.add(question)
                    await db.flush()
                    await db.execute(
                        question_tags.insert().values(question_id=question.id, tag_id=tag.id)
                    )
                    written[topic.name] = written.get(topic.name, 0) + 1
        await db.commit()
        await metrics.refresh_user(db, author_id)
    return written


async def main() -> None:
    factory = _get_session_factory()
    removed, admin_id = await clear(factory)
    if admin_id is None:
        raise SystemExit("no system administrator to own the seeded questions")
    written = await seed(factory, admin_id)
    total = sum(written.values())
    print(f"cleared: {removed}")
    print(f"seeded {total} questions across {len(written)} topics")

    # The files behind the deleted rows are no longer findable from the database,
    # so they are removed here or not at all.
    from app.config import get_config

    root = get_config().upload_dir
    for folder in ("media", "solutions"):
        directory = root / folder
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file():
                    path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
