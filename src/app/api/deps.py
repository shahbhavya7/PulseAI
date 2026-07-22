"""Shared FastAPI dependencies.

Phase 1 auth is intentionally a **stub**: no OAuth, no passwords. A caller
identifies itself with the ``X-User-Id`` header. When the header is omitted we
fall back to the fixed :data:`~app.db.seed.DEV_USER_ID`, so local curls "just
work". The referenced user is created on demand, so a fresh database never 404s
the dev user.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.seed import DEV_USER_ID, ensure_dev_user
from app.db.session import get_db
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> User:
    """Resolve the acting user from the ``X-User-Id`` header (dev stub).

    * No header → the fixed dev user (seeded on demand).
    * A malformed UUID → 400.
    * A well-formed but unknown id → 404 (except the dev id, which is seeded).
    """
    if x_user_id is None:
        return ensure_dev_user(db)

    try:
        user_id = UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id must be a valid UUID",
        ) from exc

    if user_id == DEV_USER_ID:
        return ensure_dev_user(db)

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user with id {user_id}",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
