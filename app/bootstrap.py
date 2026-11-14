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
                continue
            try:
                coltype = column.type.compile(dialect=sync_conn.dialect)
            except Exception:
                coltype = str(column.type)
            nullable = "" if column.nullable else " NOT NULL"
            sync_conn.execute(
                text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {coltype}{nullable}")
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
    logger.info("bootstrap complete, %s seed statements applied", statements)


async def taxonomy_counts(engine: AsyncEngine) -> tuple[int, int]:
    from app.db import _get_session_factory

    factory = _get_session_factory()
    async with factory() as session:
        subjects = (await session.execute(select(func.count()).select_from(Subject))).scalar_one()
        topics = (await session.execute(select(func.count()).select_from(Topic))).scalar_one()
    return int(subjects), int(topics)
