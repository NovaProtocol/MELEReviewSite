from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        from app.config import get_config

        config = get_config()
        _engine = create_async_engine(
            config.db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with _get_session_factory()() as session:
        yield session
