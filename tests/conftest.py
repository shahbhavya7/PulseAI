"""Shared pytest fixtures.

Tests here exercise the app in isolation: dependency probes are overridden so
the health/readiness suite runs without a live Postgres or Redis.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Ensure a deterministic environment before app modules read settings.
os.environ.setdefault("PULSE_ENV", "test")
os.environ.setdefault("PULSE_DEBUG", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient bound to the application, with lifespan events run."""
    with TestClient(app) as test_client:
        yield test_client
