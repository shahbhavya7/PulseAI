"""Schemas for the auth endpoints."""

from __future__ import annotations

from uuid import UUID

from app.schemas.base import APIModel


class CurrentUserResponse(APIModel):
    """The authenticated user, returned by ``GET /auth/me``."""

    id: UUID
    email: str
    full_name: str | None
    role: str
    oauth_provider: str | None


class ProvidersResponse(APIModel):
    """Which sign-in providers are configured (drives the sign-in buttons)."""

    providers: list[str]
