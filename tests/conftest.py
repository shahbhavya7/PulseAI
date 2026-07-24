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


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force the test suite to be key-independent.

    Tests must never call the real OpenAI API or depend on a developer's ``.env``
    key. Every test runs with the key cleared; tests that need a working model
    inject a fake analyzer/summarizer/vector-store. The graceful-degradation
    tests rely on this being absent.
    """
    from app.core.config import get_settings
    from app.services import llm

    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    llm.get_openai_client.cache_clear()
    yield
    llm.get_openai_client.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient bound to the application, with lifespan events run."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def require_db() -> None:
    """Skip a test when no Postgres is reachable (keeps the suite hermetic)."""
    from app.db.session import ping_db

    if not ping_db():
        pytest.skip("Postgres not available; skipping DB-backed test")
