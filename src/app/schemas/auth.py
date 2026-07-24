"""Schemas for the auth endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.base import APIModel


class CurrentUserResponse(APIModel):
    """The authenticated user, returned by ``GET /auth/me``."""

    id: UUID
    email: str
    full_name: str | None
    role: str
    oauth_provider: str | None


class ProvidersResponse(APIModel):
    """Which sign-in options are available (drives the sign-in UI)."""

    providers: list[str]  # OAuth providers, e.g. ["google"]
    email: bool = False  # whether email/password sign-in is enabled


class RegisterRequest(APIModel):
    """Body for ``POST /auth/register`` (email/password sign-up)."""

    # A light pattern check keeps the dependency footprint small; the service
    # normalises (lowercase/strip) and enforces uniqueness.
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(APIModel):
    """Body for ``POST /auth/login/email``."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)
