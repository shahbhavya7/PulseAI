"""Schemas for the health and readiness endpoints."""

from __future__ import annotations

from app.schemas.base import APIModel


class HealthResponse(APIModel):
    """Liveness payload — the process is up and serving requests."""

    status: str
    service: str
    version: str


class DependencyStatus(APIModel):
    """Health of a single downstream dependency."""

    name: str
    ok: bool


class ReadinessResponse(APIModel):
    """Readiness payload — whether the app can serve real traffic.

    ``ready`` is the logical AND of every dependency's ``ok`` flag.
    """

    ready: bool
    dependencies: list[DependencyStatus]
