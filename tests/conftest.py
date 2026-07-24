"""Shared pytest fixtures.

Tests here exercise the app in isolation: dependency probes are overridden so
the health/readiness suite runs without a live Postgres or Redis.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

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
    from app.schemas.ai import TicketAnalysis
    from app.services import llm, pipeline

    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    llm.get_openai_client.cache_clear()

    # Replace the Redis analysis cache with a fresh in-memory dict per test.
    # Redis persists across runs, so a stored result could shadow a test's mock
    # analyzer and make issue counts flaky; a per-test dict keeps cache behaviour
    # working (test_analyze_api's idempotency test still sees a hit) while being
    # fully isolated between tests.
    store: dict[str, TicketAnalysis] = {}
    monkeypatch.setattr(pipeline, "get_cached_analysis", store.get)
    monkeypatch.setattr(
        pipeline, "set_cached_analysis", lambda h, a: store.__setitem__(h, a)
    )

    llm.get_openai_client.cache_clear()
    yield
    llm.get_openai_client.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient bound to the application, with lifespan events run.

    Auth overrides applied via :func:`as_user` are cleared after each test.
    """
    from app.api.deps import get_current_user

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def as_user(client: TestClient) -> Callable[[str], str]:
    """Authenticate the TestClient as a given user id (real-auth replacement for
    the old ``X-User-Id`` header).

    Returns a setter: ``as_user(user_id)`` overrides ``get_current_user`` to load
    that user from the DB for every request, exactly as a valid session cookie
    would. Returns the id for convenience.
    """
    from uuid import UUID

    from app.api.deps import get_current_user
    from app.db.session import get_sessionmaker
    from app.models.user import User

    def _login(user_id: str) -> str:
        def _override() -> User:
            with get_sessionmaker()() as db:
                user = db.get(User, UUID(user_id))
                assert user is not None, f"test user {user_id} not found"
                db.expunge(user)
                return user

        app.dependency_overrides[get_current_user] = _override
        return user_id

    return _login


@pytest.fixture
def require_db() -> None:
    """Skip a test when no Postgres is reachable (keeps the suite hermetic)."""
    from app.db.session import ping_db

    if not ping_db():
        pytest.skip("Postgres not available; skipping DB-backed test")
