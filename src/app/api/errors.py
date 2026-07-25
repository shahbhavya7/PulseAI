"""Global exception handlers — turn infrastructure failures into clean 5xx.

Domain routes already map their own typed errors (``LLMError`` → 503,
``IngestionError`` → 4xx, ``ChatError`` → 404, …). These handlers are the safety
net for the *un*-typed failures a live request can still hit — chiefly the
database going away mid-request — so the client gets a small JSON body with a
stable ``code`` instead of a leaked stack trace / bare 500.

Registered in :func:`app.main.create_app`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger(__name__)


def _json(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )


async def _handle_db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Any unhandled database error → 503 (the DB is the dependency at fault)."""
    logger.warning("Database error on %s %s: %s", request.method, request.url.path, exc)
    return _json(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "database_unavailable",
        "The database is temporarily unavailable. Please try again shortly.",
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch-all: log the detail, return a generic 500 (no leak)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _json(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Something went wrong. Please try again.",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach the infrastructure-failure handlers to ``app``."""
    app.add_exception_handler(SQLAlchemyError, _handle_db_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
