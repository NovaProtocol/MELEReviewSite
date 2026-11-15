"""The adaptive ADD COLUMN path, including a populated table.

The bug this covers only reproduced on MySQL: adding a NOT NULL DATETIME column
to a table with rows raised error 1292 because the existing rows would get the
zero date. SQLite accepts it silently, so the check here is the shape of what the
migration does rather than the database's objection.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.bootstrap import _adaptive_sync, _backfill_expression
from app.models import Base


def test_backfill_expression_covers_every_type_it_must():
    assert _backfill_expression("DATETIME") == "CURRENT_TIMESTAMP"
    assert _backfill_expression("TIMESTAMP") == "CURRENT_TIMESTAMP"
    assert _backfill_expression("INTEGER") == "0"
    assert _backfill_expression("BIGINT") == "0"
    assert _backfill_expression("BOOLEAN") == "0"
    assert _backfill_expression("VARCHAR(32)") == "''"


def test_the_adaptive_pass_creates_and_extends_a_populated_schema(tmp_path):
    """Run the pass against a database that already has rows in an old shape."""
    url = f"sqlite+aiosqlite:///{tmp_path}/mig.db"
    engine = create_async_engine(url)

    async def scenario():
        async with engine.begin() as conn:
            # An attempt table in its pre-release shape, with a row already in it.
            await conn.execute(
                text(
                    "CREATE TABLE question_attempts ("
                    "id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL, "
                    "user_id INTEGER NOT NULL, chosen VARCHAR(1) NOT NULL, "
                    "is_correct BOOLEAN NOT NULL, "
                    "date_created DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO question_attempts "
                    "(question_id, user_id, chosen, is_correct) VALUES (1, 1, 'A', 0)"
                )
            )

        # The production migration: three new NOT NULL columns on a populated
        # table. On MySQL this raised 1292 before the fix.
        async with engine.begin() as conn:
            await conn.run_sync(_adaptive_sync)

        async with engine.begin() as conn:
            columns = await conn.run_sync(
                lambda sync: {c["name"] for c in inspect(sync).get_columns("question_attempts")}
            )
            row = (
                await conn.execute(
                    text("SELECT attempts, first_correct, chosen FROM question_attempts LIMIT 1")
                )
            ).one()
        return columns, row

    columns, row = asyncio.run(scenario())
    assert {"first_selection", "first_correct", "attempts", "date_modified"} <= columns
    # The pre-existing row got a usable value rather than a NULL or a zero date.
    assert int(row[0]) == 0
    assert bool(row[1]) is False
    assert row[2] == "A"

    asyncio.run(engine.dispose())


def test_the_models_carry_the_new_attempt_columns():
    columns = {c.name for c in Base.metadata.tables["question_attempts"].columns}
    assert {"first_selection", "first_correct", "attempts", "date_modified"} <= columns
    for name in ("first_correct", "attempts"):
        assert not Base.metadata.tables["question_attempts"].c[name].nullable


def test_the_user_row_carries_the_metrics():
    columns = {c.name for c in Base.metadata.tables["users"].columns}
    expected = {
        "metric_questions",
        "metric_answered",
        "metric_first_correct",
        "metric_solved",
        "metric_attempts",
    }
    assert expected <= columns


def test_the_default_repair_only_targets_a_missing_default():
    """The guard matters: without it every boot would issue DDL on every column."""
    from app.bootstrap import _repair_server_default

    calls = []

    class Dialect:
        name = "mysql"

    class Connection:
        dialect = Dialect()

        def execute(self, statement):
            calls.append(str(statement))

    class Default:
        # SQLAlchemy renders func.now() as this expression; the migration has to
        # translate it, because `DEFAULT now()` is a MySQL syntax error.
        arg = "now()"

    class FakeType:
        @staticmethod
        def compile(dialect=None):
            assert dialect is not None, "the repair must compile against the dialect"
            return "DATETIME"

    class Column:
        name = "date_modified"
        server_default = Default()
        nullable = False
        type = FakeType()

    class NoDefault:
        name = "plain"
        server_default = None
        nullable = True

    # SQLite is skipped wholesale, and MySQL with a default already in place must
    # produce no statement at all.
    _repair_server_default(Connection(), "t", Column(), {"default": None}, is_mysql=False)
    _repair_server_default(
        Connection(), "t", Column(), {"default": "CURRENT_TIMESTAMP"}, is_mysql=True
    )
    _repair_server_default(Connection(), "t", NoDefault(), {"default": None}, is_mysql=True)
    assert calls == []

    # Only the genuinely missing default produces the ALTER.
    _repair_server_default(Connection(), "t", Column(), {"default": None}, is_mysql=True)
    assert len(calls) == 1
    # MySQL 8.4 only accepts a DEFAULT through MODIFY COLUMN, restating the type.
    assert "MODIFY COLUMN date_modified DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP" in calls[0]
    assert "now()" not in calls[0]
