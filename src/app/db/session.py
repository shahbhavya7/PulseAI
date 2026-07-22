"""Engine, session factory, and the FastAPI ``get_db`` dependency.

The engine and ``sessionmaker`` are created lazily and cached for the process.
``get_db`` yields a session per request and guarantees it is closed; it rolls
back on error so a failed request never leaks a dirty transaction.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide cached SQLAlchemy engine."""
    settings = get_settings()
    logger.debug("Creating SQLAlchemy engine")
    return create_engine(
        settings.sqlalchemy_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        echo=settings.debug,
        future=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide cached session factory."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session.

    Commits are the caller's responsibility. The session is rolled back on any
    exception and always closed.
    """
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_db() -> bool:
    """Return True if the database answers ``SELECT 1``, False otherwise.

    Never raises — intended for readiness checks that must degrade gracefully.
    """
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — health probe must not propagate
        logger.warning("Database ping failed: %s", exc)
        return False
