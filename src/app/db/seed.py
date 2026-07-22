"""Development seed data.

Phase 1 auth is a **dev-user stub**: there is exactly one fixed user, identified
by :data:`DEV_USER_ID`. Requests select it via the ``X-User-Id`` header (see
:mod:`app.api.deps`). This module is the single source of that fixed identity and
an idempotent function to persist it.

Run standalone with::

    python -m app.db.seed
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.models.enums import UserRole
from app.models.user import User

logger = get_logger(__name__)

# Fixed identity for the dev-user stub. Stable across restarts so the header
# value is predictable in docs, tests, and manual curls.
DEV_USER_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_EMAIL = "dev@pulseai.local"
DEV_USER_NAME = "Dev User"


def ensure_dev_user(db: Session) -> User:
    """Create the fixed dev user if absent; return it either way (idempotent)."""
    user = db.get(User, DEV_USER_ID)
    if user is not None:
        return user

    # Guard against a pre-existing row with the same email but a different id.
    existing = db.scalar(select(User).where(User.email == DEV_USER_EMAIL))
    if existing is not None:
        return existing

    user = User(
        id=DEV_USER_ID,
        email=DEV_USER_EMAIL,
        full_name=DEV_USER_NAME,
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Seeded dev user id=%s email=%s", DEV_USER_ID, DEV_USER_EMAIL)
    return user


def main() -> None:
    """Entry point for ``python -m app.db.seed``."""
    with get_sessionmaker()() as db:
        ensure_dev_user(db)
    logger.info("Dev user seed complete")


if __name__ == "__main__":
    main()
