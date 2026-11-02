"""Async SQLAlchemy engine/session against Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from . import config

engine = create_async_engine(config.DATABASE_URL, pool_pre_ping=True, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


# `create_all` only creates missing tables — it never alters a table that
# already exists. There's no migration tool here (not worth it at this
# scale), so a handful of additive, backward-safe column additions are
# patched in by hand. Each is a no-op once already applied.
_PATCH_STATEMENTS = [
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS owner_email VARCHAR(320) NOT NULL DEFAULT ''",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS instructions TEXT NOT NULL DEFAULT ''",
    # Superseded by the single free-text `instructions` column above.
    "ALTER TABLE meeting_sessions DROP COLUMN IF EXISTS do_summary",
    "ALTER TABLE meeting_sessions DROP COLUMN IF EXISTS do_present",
    "ALTER TABLE meeting_sessions DROP COLUMN IF EXISTS document_ids",
    # One optional attached document per request, presented slide-by-slide
    # on join — distinct from the dropped document_ids above, which scoped
    # retrieval; this never does.
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS pages JSON",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_images JSON",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS document_id VARCHAR(32) REFERENCES documents(id) ON DELETE SET NULL",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS document_title VARCHAR(256)",
]


async def init_models() -> None:
    from . import models  # noqa: F401 - register tables on Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for statement in _PATCH_STATEMENTS:
            await conn.execute(text(statement))


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
