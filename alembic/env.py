from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context  # type: ignore[attr-defined]

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure project root on sys.path for `api` imports when running via CLI
# (alembic.ini already prepends ".", but be defensive)
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# Import metadata for autogenerate
from api.models import Base  # noqa: E402

target_metadata = Base.metadata


def _get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")  # type: ignore[no-untyped-call]
    # alembic.ini default placeholder -> override from Settings
    if not url or url == "driver://user:pass@localhost/dbname":
        try:
            from api.config import get_config

            raw = get_config().db_url
            # Alembic runs synchronously; map async drivers to sync equivalents
            url = raw.replace("+aiomysql", "+pymysql").replace("+aiosqlite", "")
            # Normalize sqlite:// url already sync
            config.set_main_option("sqlalchemy.url", url)
        except Exception:
            pass
    else:
        # Normalize any async driver passed via CLI/config
        norm = url.replace("+aiomysql", "+pymysql").replace("+aiosqlite", "")
        if norm != url:
            config.set_main_option("sqlalchemy.url", norm)
            url = norm
    return url or ""  # type: ignore[return-value]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    _get_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
