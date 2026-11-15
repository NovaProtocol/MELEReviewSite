"""Startup schema work: legacy reset, adaptive migration, seed, admin account.

Order matters. The reset has to run before ``create_all`` or the new tables would
be created next to the old ones; the seed has to run after the tables exist; the
admin account last, because it reads permissions and writes a hash.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import permissions
from app.models import Base, Subject, Topic, User
from app.security import hash_password, new_uid, verify_password

logger = logging.getLogger("melereview.bootstrap")

SEED_FILE = Path(__file__).resolve().parent.parent / "mysql" / "seed" / "taxonomy.sql"

# The retired media-pin reviewer: profiles with pins, questions with an answer
# index, solutions as JSON blocks. Dropped in dependency order with FK checks off.
LEGACY_TABLES = (
    "question_tags",
    "question_flags",
    "solutions",
    "questions",
    "tags",
    "accounts",
)


def _split_statements(raw: str) -> list[str]:
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(stripped)
    return [s for s in lines if s.endswith(";")]


async def reset_legacy_schema(engine: AsyncEngine) -> list[str]:
    """Drop the retired tables once, when the new users table is absent."""
    dropped: list[str] = []
    async with engine.begin() as conn:
        present = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        if "users" in present:
            return dropped
        legacy = [t for t in LEGACY_TABLES if t in present]
        if not legacy:
            return dropped
        is_mysql = conn.dialect.name == "mysql"
        if is_mysql:
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        try:
            for table in legacy:
                await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                dropped.append(table)
        finally:
            if is_mysql:
                await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    if dropped:
        logger.warning("dropped retired tables: %s", ", ".join(dropped))
    return dropped


def _backfill_expression(coltype: str) -> str | None:
    """A value a pre-existing row can carry for a newly added NOT NULL column."""
    upper = coltype.upper()
    if "INT" in upper or "BOOL" in upper:
        return "0"
    if "DATETIME" in upper or "TIMESTAMP" in upper:
        return "CURRENT_TIMESTAMP"
    if "CHAR" in upper or "TEXT" in upper:
        return "''"
    return None


def _repair_server_default(sync_conn, table: str, column, existing, is_mysql: bool) -> None:
    """Re-apply a ``server_default`` that an earlier migration left off.

    A column added while the migration was still adding columns nullable has no
    default, so an INSERT that omits it fails with error 1364. The model says what
    the default should be, so the table is brought back in line with it. Only
    touches a column that is actually missing its default, so a normal boot issues
    no DDL at all.
    """
    if column.server_default is None or not is_mysql:
        return
    if existing.get("default") is not None:
        return
    try:
        raw = column.server_default.arg
        wanted = raw.text if hasattr(raw, "text") else str(raw)
    except Exception:
        return
    wanted = str(wanted).strip()
    # MySQL wants CURRENT_TIMESTAMP, not the SQLAlchemy expression that produced
    # it; `now()` is a syntax error in a DEFAULT clause.
    if wanted.lower().replace(" ", "") in {"now()", "currenttimestamp()", "localtimestamp()"}:
        wanted = "CURRENT_TIMESTAMP"
    if not wanted:
        return
    # MySQL 8.4 rejects `ALTER COLUMN ... SET DEFAULT` for a DATETIME: the default
    # only takes through MODIFY COLUMN, which restates the whole definition. Type
    # and nullability come from the model, so the restatement drops neither.
    try:
        coltype = column.type.compile(dialect=sync_conn.dialect)
    except Exception:
        return
    nullable = "" if column.nullable else " NOT NULL"
    sync_conn.execute(
        text(
            f"ALTER TABLE {table} MODIFY COLUMN {column.name} {coltype}{nullable} DEFAULT {wanted}"
        )
    )


def _adaptive_sync(sync_conn) -> None:
    is_mysql = sync_conn.dialect.name == "mysql"
    insp = inspect(sync_conn)
    existing = insp.get_table_names()
    if set(Base.metadata.tables) - set(existing):
        if is_mysql:
            sync_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        Base.metadata.create_all(bind=sync_conn)
        if is_mysql:
            sync_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        insp = inspect(sync_conn)
        existing = insp.get_table_names()

    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        try:
            columns = {c["name"]: c for c in insp.get_columns(table.name)}
        except Exception:
            continue
        for column in table.columns:
            if column.name in columns:
                _repair_server_default(
                    sync_conn, table.name, column, columns[column.name], is_mysql
                )
                continue
            try:
                coltype = column.type.compile(dialect=sync_conn.dialect)
            except Exception:
                coltype = str(column.type)
            # A NOT NULL column added to a populated table has no value for the
            # rows already there. MySQL rejects the implicit zero date (error
            # 1292) and SQLite accepts it, so this only breaks in production.
            # Add it nullable, fill it, then tighten: a permanent DEFAULT would
            # keep masking a writer that forgot the column.
            sync_conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {coltype}"))
            if not column.nullable:
                fill = _backfill_expression(str(coltype))
                if fill is not None:
                    sync_conn.execute(
                        text(
                            f"UPDATE {table.name} SET {column.name} = {fill} "
                            f"WHERE {column.name} IS NULL"
                        )
                    )
                if is_mysql:
                    # SQLite cannot tighten a column, and it does not enforce
                    # NOT NULL on an ALTER the way MySQL does, so the UPDATE is
                    # all it needs.
                    sync_conn.execute(
                        text(
                            f"ALTER TABLE {table.name} MODIFY COLUMN "
                            f"{column.name} {coltype} NOT NULL"
                        )
                    )


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_adaptive_sync)


async def seed_taxonomy(engine: AsyncEngine, path: Path | None = None) -> int:
    """Execute the taxonomy seed. Guarded statements make it safe to re-run."""
    source = path or SEED_FILE
    if not source.exists():
        logger.error("taxonomy seed missing at %s", source)
        return 0
    statements = _split_statements(source.read_text(encoding="utf-8"))
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
    return len(statements)


async def ensure_system_admin(engine: AsyncEngine, username: str, password: str) -> None:
    """Reconcile the system administrator with ADMIN_USER / ADMIN_PASS.

    The username is claimed only when no administrator exists, so a rename in the
    interface survives a restart. The password is the environment's on every boot,
    which is what makes the compose variables the source of truth.
    """
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        admin = (
            (await session.execute(select(User).where(User.is_system_admin.is_(True))))
            .scalars()
            .first()
        )
        if admin is None:
            admin = (
                (await session.execute(select(User).where(User.username == username)))
                .scalars()
                .first()
            )
            if admin is None:
                admin = User(
                    uid=new_uid(),
                    username=username,
                    email=f"{username}@melereview.local",
                    password_hash=hash_password(password),
                    permissions=permissions.ALL,
                    is_system_admin=True,
                )
                session.add(admin)
                await session.commit()
                logger.warning("created system administrator '%s'", username)
                return
            admin.is_system_admin = True
            admin.permissions = permissions.ALL
            admin.status = "active"
            admin.status_reason = None
            admin.status_root_user_id = None

        admin.permissions = permissions.ALL
        if not verify_password(password, admin.password_hash):
            admin.password_hash = hash_password(password)
            logger.warning("reconciled the administrator password from ADMIN_PASS")
        await session.commit()


async def bootstrap(engine: AsyncEngine, admin_user: str, admin_pass: str) -> None:
    await reset_legacy_schema(engine)
    for attempt in range(1, 11):
        try:
            await create_schema(engine)
            break
        except Exception as exc:
            if attempt == 10:
                logger.exception("schema creation failed after 10 attempts")
                raise
            logger.warning("database not ready (%s/10): %s", attempt, exc)
            await asyncio.sleep(3)
    statements = await seed_taxonomy(engine)
    await ensure_system_admin(engine, admin_user, admin_pass)
    await refresh_all_metrics(engine)
    logger.info("bootstrap complete, %s seed statements applied", statements)


async def refresh_all_metrics(engine: AsyncEngine) -> int:
    """Recompute every member's cached numbers once at startup.

    Cheap (two aggregates per member), and it means a column added by an adaptive
    migration is filled from the attempt rows rather than reading as zero.
    """
    from app.services import metrics

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user_ids = [int(row[0]) for row in (await session.execute(select(User.id))).all()]
        for user_id in user_ids:
            await metrics.refresh_user(session, user_id)
        await session.commit()
    return len(user_ids)


async def taxonomy_counts(engine: AsyncEngine) -> tuple[int, int]:
    from app.db import _get_session_factory

    factory = _get_session_factory()
    async with factory() as session:
        subjects = (await session.execute(select(func.count()).select_from(Subject))).scalar_one()
        topics = (await session.execute(select(func.count()).select_from(Topic))).scalar_one()
    return int(subjects), int(topics)
