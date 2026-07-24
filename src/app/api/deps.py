"""Shared FastAPI dependencies.

Auth (Phase 5) is **real OIDC**: after signing in with Google/Apple the browser
holds a signed session JWT in an httpOnly cookie. ``get_current_user`` reads that
cookie, verifies it, loads the user, and 401s otherwise. Every route that depends
on :data:`CurrentUser` is therefore authenticated and scoped to that user.

Tests don't perform the OAuth dance; they override ``get_current_user`` via
``app.dependency_overrides`` to inject a known user (see ``tests/conftest.py``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth import AuthError, decode_session_token

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    session: Annotated[str | None, Cookie(alias=get_settings().session_cookie_name)] = None,
) -> User:
    """Resolve the authenticated user from the session cookie.

    * No cookie → 401 (``not_authenticated``).
    * Bad/expired token → 401 (``invalid_session``).
    * Valid token but the user is gone or deactivated → 401.
    """
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "not_authenticated", "message": "Sign in to continue."},
        )
    try:
        user_id = decode_session_token(session)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_session", "message": exc.message},
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_session", "message": "Session no longer valid."},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
