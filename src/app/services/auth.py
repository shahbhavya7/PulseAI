"""Authentication service — session JWTs and OAuth user provisioning.

Two concerns live here, kept independent of FastAPI so they're unit-testable:

* **Session tokens** — after a successful OAuth login we mint a signed JWT (HS256)
  carrying the user id. It rides in an httpOnly cookie. `issue_session_token`
  creates one; `decode_session_token` verifies it (signature + expiry) and
  returns the user id, or raises :class:`AuthError`.
* **User provisioning** — `upsert_oauth_user` maps a provider identity
  (provider + subject + email) to a :class:`~app.models.user.User`, creating one
  on first login and matching an existing account on return visits.

Nothing here trusts client-supplied ids: the subject/email come from the
provider's verified id-token (validated by Authlib in the callback route).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from fastapi import Response

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import UserRole
from app.models.user import User

logger = get_logger(__name__)


class AuthError(Exception):
    """Raised when a session token is missing, malformed, or expired."""

    def __init__(self, message: str = "Not authenticated") -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Session JWTs
# ---------------------------------------------------------------------------


def issue_session_token(user: User) -> str:
    """Mint a signed session JWT for ``user`` (subject = user id)."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.session_ttl_seconds)).timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_session_token(token: str) -> UUID:
    """Verify a session JWT and return its user id.

    Raises :class:`AuthError` on any problem (bad signature, expiry, malformed
    subject) — the caller maps that to a 401.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid session") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise AuthError("Invalid session")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise AuthError("Invalid session") from exc


def set_session_cookie(response: Response, user: User) -> None:
    """Attach the session JWT to ``response`` as an httpOnly cookie."""
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issue_session_token(user),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
        domain=settings.session_cookie_domain,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie (sign-out)."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        path="/",
    )


# ---------------------------------------------------------------------------
# OAuth user provisioning
# ---------------------------------------------------------------------------


def upsert_oauth_user(
    db: Session,
    *,
    provider: str,
    subject: str,
    email: str,
    full_name: str | None,
) -> User:
    """Find or create the user for a verified provider identity.

    Matching order:

    1. by (provider, subject) — the stable identity; return the existing user
       (refreshing name/email if the provider changed them),
    2. else by email — an account that predates OAuth or signed in with another
       provider using the same verified email; attach this identity to it,
    3. else create a brand-new user.
    """
    email = email.strip().lower()

    user = db.scalar(
        select(User).where(
            User.oauth_provider == provider, User.oauth_subject == subject
        )
    )
    if user is not None:
        # Keep profile fields fresh, but never downgrade a known name to None.
        if email and user.email != email:
            user.email = email
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        db.commit()
        db.refresh(user)
        return user

    existing = db.scalar(select(User).where(User.email == email)) if email else None
    if existing is not None:
        existing.oauth_provider = provider
        existing.oauth_subject = subject
        if full_name and not existing.full_name:
            existing.full_name = full_name
        db.commit()
        db.refresh(existing)
        logger.info("Linked %s identity to existing user id=%s", provider, existing.id)
        return existing

    user = User(
        email=email,
        full_name=full_name,
        role=UserRole.MEMBER,
        is_active=True,
        oauth_provider=provider,
        oauth_subject=subject,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user id=%s via %s", user.id, provider)
    return user
