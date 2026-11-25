"""Database session management and async engine configuration."""

from typing import AsyncGenerator

from app.core.config import get_settings
from app.storage.models import Base
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    global _engine
    if _engine is None or db_url is not None:
        url = db_url or get_settings().database_url
        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            echo=False,
        )
        if db_url is None:
            _engine = engine
        return engine
    return _engine


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    eng = engine or get_engine()
    if _session_factory is None or engine is not None:
        factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
        if engine is None:
            _session_factory = factory
        return factory
    return _session_factory


async def init_tables(engine: AsyncEngine) -> None:
    """Create all schema tables asynchronously."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables(engine: AsyncEngine) -> None:
    """Drop all tables asynchronously (for testing cleanup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def reset_db_engine() -> None:
    """Dispose and reset engine and session factory singleton."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
