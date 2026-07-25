"""FastAPI application factory and ASGI entrypoint.

Run locally with::

    uvicorn app.main:app --reload --app-dir src
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api.errors import register_error_handlers
from app.api.routes import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: configure logging on startup, log shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger("app.main")
    from app.services.oauth import enabled_providers

    logger.info(
        "Starting %s (env=%s, version=%s, auth_providers=%s)",
        settings.project_name,
        settings.env,
        __version__,
        enabled_providers() or "none",
    )
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
    # Allow the browser dashboard (Next.js) to call the API cross-origin *with
    # credentials* (the session cookie). allow_credentials requires explicit
    # origins (no "*").
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Authlib stashes the OAuth `state`/nonce in a server-signed session cookie
    # between the login redirect and the callback. This is separate from our own
    # session JWT and only used during the handshake.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.oauth_state_secret.get_secret_value(),
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )
    # Turn unhandled infrastructure failures (DB down mid-request, etc.) into
    # clean 5xx JSON instead of leaked stack traces.
    register_error_handlers(app)
    # Health routes live at the root; domain routes sit under the API prefix.
    app.include_router(api_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
