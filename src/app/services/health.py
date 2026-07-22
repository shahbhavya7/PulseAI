"""Health/readiness service.

Centralizes the dependency probes so the route layer only shapes the response.
Every probe is non-raising: a down dependency yields ``ok=False`` rather than
an exception, letting readiness degrade to 503 without crashing the request.
"""

from __future__ import annotations

from app import __version__
from app.core.config import get_settings
from app.core.redis import ping_redis
from app.db.session import ping_db
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse


class HealthService:
    """Assembles liveness and readiness payloads."""

    @staticmethod
    def liveness() -> HealthResponse:
        """Return the liveness payload. Does not touch any dependency."""
        settings = get_settings()
        return HealthResponse(
            status="ok",
            service=settings.project_name,
            version=__version__,
        )

    @staticmethod
    def readiness() -> ReadinessResponse:
        """Probe every dependency and return an aggregated readiness payload."""
        dependencies = [
            DependencyStatus(name="database", ok=ping_db()),
            DependencyStatus(name="redis", ok=ping_redis()),
        ]
        return ReadinessResponse(
            ready=all(dep.ok for dep in dependencies),
            dependencies=dependencies,
        )
