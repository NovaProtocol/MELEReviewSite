"""Tests for adaptive _init_db (sqlalchemy only)."""

from __future__ import annotations

import contextlib
import pathlib


def test_adaptive_code_uses_sqlalchemy():
    """_init_db must be adaptive via sqlalchemy only."""
    txt = pathlib.Path("api/app.py").read_text()
    # must use sqlalchemy inspector
    assert "inspect" in txt, "missing sqlalchemy inspect usage"
    assert "get_table_names" in txt, "missing get_table_names"
    assert "get_columns" in txt, "missing get_columns"
    assert "CHAR_LENGTH" in txt or "char_length" in txt, "missing CHAR_LENGTH check"
    assert "func.max" in txt or "MAX" in txt, "missing MAX check"
    assert "FOREIGN_KEY_CHECKS" in txt, "missing SET FOREIGN_KEY_CHECKS"
    assert "pymysql" not in txt.lower(), "should not use pymysql, sqlalchemy only"
    assert "ADD COLUMN" in txt, "missing ADD COLUMN handling"
    assert "MODIFY" in txt, "missing MODIFY handling"
    assert "RuntimeError" in txt, "missing clip RuntimeError"


def test_adaptive_migration_handles_missing_column(monkeypatch):
    """Simulate table exists but missing column, ensure ADD works."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import api.app as app_module

    executed = []

    def run_sync_side_effect(func):
        mock_conn = MagicMock()
        mock_conn.dialect.name = "sqlite"
        mock_insp = MagicMock()
        mock_insp.get_table_names.return_value = [
            "accounts",
            "questions",
            "tags",
            "solutions",
            "question_tags",
            "question_flags",
        ]

        def get_cols(tbl):
            if tbl == "questions":
                # missing account_id
                return [
                    {"name": "id", "type": MagicMock(length=None)},
                    {"name": "question_text", "type": MagicMock(length=None)},
                    {"name": "choice_a", "type": MagicMock(length=None)},
                    {"name": "choice_b", "type": MagicMock(length=None)},
                    {"name": "choice_c", "type": MagicMock(length=None)},
                    {"name": "choice_d", "type": MagicMock(length=None)},
                ]
            return [{"name": "id", "type": MagicMock(length=None)}]

        mock_insp.get_columns.side_effect = get_cols

        def exec_sql(sql, *a, **kw):
            executed.append(str(sql))

        mock_conn.execute.side_effect = exec_sql
        mock_conn.scalar.return_value = None

        # Patch inspect used inside app.py
        # Try both possible import locations
        patches = []
        # api.app.inspect if imported there
        try:
            p = patch("api.app.inspect", return_value=mock_insp)
            p.start()
            patches.append(p)
        except Exception:
            pass
        # also patch sqlalchemy.inspect as fallback
        p2 = patch("sqlalchemy.inspect", return_value=mock_insp)
        p2.start()
        patches.append(p2)

        # patch create_all to avoid real DB
        p3 = patch("api.models.Base.metadata.create_all")
        m3 = p3.start()
        patches.append(p3)

        try:
            func(mock_conn)
            # should not have called create_all because tables exist
            m3.assert_not_called()
        finally:
            for pp in patches:
                pp.stop()

        assert any("ADD COLUMN" in s and "account_id" in s for s in executed), (
            f"ADD not executed: {executed}"
        )
        return None

    mock_conn_obj = MagicMock()

    # run_sync is async in sqlalchemy async engine? Actually await conn.run_sync(fn)
    # In AsyncConnection, run_sync is async def, so we need AsyncMock
    # But our side_effect function is sync that returns None, need to make it awaitable
    # Use AsyncMock with side_effect that calls our function
    async def fake_run_sync(fn):
        return run_sync_side_effect(fn)

    mock_conn_obj.run_sync = AsyncMock(side_effect=fake_run_sync)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn_obj
    mock_ctx.__aexit__.return_value = False
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_ctx

    monkeypatch.setattr("api.db._get_engine", lambda: mock_engine)
    # also handle if app.py keeps reference
    with contextlib.suppress(Exception):
        monkeypatch.setattr("api.app._get_engine", lambda: mock_engine, raising=False)
    monkeypatch.setattr("api.app.asyncio.sleep", AsyncMock())

    import asyncio

    asyncio.run(app_module._init_db())


def test_adaptive_shrink_checks_clip(monkeypatch):
    """Insert row with len 100, try to shrink to 50 -> should raise."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import sqlalchemy as sa

    import api.app as app_module

    def run_sync_side_effect(func):
        mock_conn = MagicMock()
        mock_conn.dialect.name = "mysql"
        mock_insp = MagicMock()
        mock_insp.get_table_names.return_value = [
            "accounts",
            "questions",
            "tags",
            "solutions",
            "question_tags",
            "question_flags",
        ]
        col_type_100 = sa.String(100)

        def get_cols(tbl):
            if tbl == "tags":
                return [
                    {"name": "id", "type": sa.Integer()},
                    {"name": "name", "type": col_type_100},
                ]
            if tbl == "accounts":
                return [
                    {"name": "id", "type": sa.Integer()},
                    {"name": "name", "type": sa.String(100)},
                    {"name": "pin", "type": sa.String(100)},
                ]
            if tbl == "questions":
                return [
                    {"name": "id", "type": sa.Integer()},
                    {"name": "account_id", "type": sa.Integer()},
                ]
            return [{"name": "id", "type": sa.Integer()}]

        mock_insp.get_columns.side_effect = get_cols
        mock_conn.scalar.return_value = 80  # would clip if shrink to 50
        mock_conn.execute = MagicMock()

        patches = []
        try:
            p = patch("api.app.inspect", return_value=mock_insp)
            p.start()
            patches.append(p)
        except Exception:
            pass
        p2 = patch("sqlalchemy.inspect", return_value=mock_insp)
        p2.start()
        patches.append(p2)

        try:
            func(mock_conn)
        finally:
            for pp in patches:
                pp.stop()
        return None

    async def fake_run_sync(fn):
        return run_sync_side_effect(fn)

    mock_conn_obj = MagicMock()
    mock_conn_obj.run_sync = AsyncMock(side_effect=fake_run_sync)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn_obj
    mock_ctx.__aexit__.return_value = False
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_ctx

    monkeypatch.setattr("api.db._get_engine", lambda: mock_engine)
    with contextlib.suppress(Exception):
        monkeypatch.setattr("api.app._get_engine", lambda: mock_engine, raising=False)
    monkeypatch.setattr("api.app.asyncio.sleep", AsyncMock())

    import asyncio

    try:
        asyncio.run(app_module._init_db())
    except RuntimeError as e:
        msg = str(e).lower()
        assert "clip" in msg or "max" in msg or "50" in msg
    else:
        raise AssertionError("expected RuntimeError due to clip")
