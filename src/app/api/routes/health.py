"""Liveness (``/health``) and readiness (``/ready``) endpoints.

``/health`` reports process liveness and always returns 200 when the app is
running. ``/ready`` probes downstream dependencies and returns 503 when any is
unavailable, so orchestrators can withhold traffic without the app crashing.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe. Returns 200 whenever the process is serving."""
    return HealthService.liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def ready(response: Response) -> ReadinessResponse:
    """Readiness probe.

    Returns 200 when all dependencies are healthy, otherwise 503 with the
    per-dependency breakdown. Dependency failures degrade the status code;
    they never raise.
    """
    result = HealthService.readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
