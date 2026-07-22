"""FastAPI application factory and ASGI entrypoint.

Run locally with::

    uvicorn app.main:app --reload --app-dir src
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: configure logging on startup, log shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger("app.main")
    logger.info(
        "Starting %s (env=%s, version=%s)",
        settings.project_name,
        settings.env,
        __version__,
    )
    # Best-effort dev-user seed (Phase 1 auth stub). Never fatal: if the DB is
    # not reachable at startup the app still boots and /health stays green.
    try:
        from app.db.seed import ensure_dev_user
        from app.db.session import get_sessionmaker

        with get_sessionmaker()() as db:
            ensure_dev_user(db)
    except Exception as exc:  # noqa: BLE001 — startup seed must not crash boot
        logger.warning("Dev-user seed skipped: %s", exc)
    yield
    logger.info("Shutting down %s", settings.project_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = get_settings()
    app = FastAPI(
        title=settings.project_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )
    # Health routes live at the root; domain routes sit under the API prefix.
    app.include_router(api_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
