"""API-failure hardening (Phase 7).

Proves the service degrades — never crashes — when a dependency is down:

* ``/ready`` returns 503 (not an exception) when the DB or Redis probe fails.
* A domain route hitting a database error returns a clean **503**, not a leaked
  500 / stack trace, via the global SQLAlchemyError handler.

These use dependency/monkeypatch fakes, so they run without any live Postgres,
Redis, or OpenAI key.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


@pytest.fixture
def bare_client() -> Iterator[TestClient]:
    """A client that surfaces handler responses (does not re-raise 5xx), so the
    global exception handlers are exercised the way a real client sees them."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---- /ready degrades, never crashes ---------------------------------------


def test_ready_ok_when_all_deps_up(
    bare_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import health

    monkeypatch.setattr(health, "ping_db", lambda: True)
    monkeypatch.setattr(health, "ping_redis", lambda: True)
    resp = bare_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_ready_degrades_to_503_when_db_down(
    bare_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import health

    monkeypatch.setattr(health, "ping_db", lambda: False)
    monkeypatch.setattr(health, "ping_redis", lambda: True)
    resp = bare_client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    db = next(d for d in body["dependencies"] if d["name"] == "database")
    assert db["ok"] is False


def test_ready_degrades_to_503_when_redis_down(
    bare_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import health

    monkeypatch.setattr(health, "ping_db", lambda: True)
    monkeypatch.setattr(health, "ping_redis", lambda: False)
    resp = bare_client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["ready"] is False


def test_ping_probes_never_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probes themselves swallow errors (return False), so readiness can't
    crash even if the client blows up."""
    from app.core import redis as redis_mod
    from app.db import session as db_mod

    def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(db_mod, "get_engine", _boom)
    monkeypatch.setattr(redis_mod, "get_redis", _boom)
    assert db_mod.ping_db() is False
    assert redis_mod.ping_redis() is False


# ---- domain route: DB error → 503, not a leaked 500 ------------------------


def test_db_error_on_domain_route_returns_503(
    bare_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When an authenticated request hits a database error, the global handler
    returns a clean 503 with a typed code — never a raw 500."""
    from uuid import uuid4

    from app.api.deps import get_current_user
    from app.db import session as db_mod
    from app.models.user import User

    # A user object that doesn't need the DB to construct.
    fake_user = User(id=uuid4(), email="x@test.local", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: fake_user

    # Make the session factory raise as if the DB is unreachable.
    def _broken_sessionmaker():  # type: ignore[no-untyped-def]
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(db_mod, "get_sessionmaker", _broken_sessionmaker)

    try:
        resp = bare_client.get("/stats")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "database_unavailable"
