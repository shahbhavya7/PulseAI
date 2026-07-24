"""Tests for the auth service and endpoints.

JWT round-trip is hermetic (no DB). User provisioning + isolation + the
``/auth/*`` endpoints require Postgres and are skipped when it's unavailable.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.user import User
from app.services.auth import AuthError, decode_session_token, issue_session_token

# ---- Session JWTs (no DB) --------------------------------------------------


def test_jwt_round_trip() -> None:
    user = User(id=uuid4(), email="a@b.com", full_name="A")
    token = issue_session_token(user)
    assert decode_session_token(token) == user.id


def test_jwt_tampered_signature_rejected() -> None:
    user = User(id=uuid4(), email="a@b.com")
    token = issue_session_token(user)
    with pytest.raises(AuthError):
        decode_session_token(token + "x")


def test_jwt_garbage_rejected() -> None:
    with pytest.raises(AuthError):
        decode_session_token("not.a.jwt")


# ---- Endpoints -------------------------------------------------------------


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "not_authenticated"


def test_providers_lists_configured(client: TestClient) -> None:
    # No provider env vars in the test env → empty list, but the endpoint works.
    resp = client.get("/auth/providers")
    assert resp.status_code == 200
    assert resp.json() == {"providers": []}


def test_login_unknown_provider_404(client: TestClient) -> None:
    resp = client.get("/auth/login/google", follow_redirects=False)
    # Google isn't configured in tests → treated as unavailable.
    assert resp.status_code == 404


def test_logout_clears_cookie(client: TestClient) -> None:
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "signed_out"


# ---- Provisioning + isolation (DB) -----------------------------------------


def test_me_returns_authenticated_user(
    client: TestClient, as_user: Callable[[str], str], require_db: None
) -> None:
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        user = User(email=f"{uuid4().hex}@test.local", full_name="Me Tester")
        db.add(user)
        db.commit()
        uid = str(user.id)

    as_user(uid)
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["id"] == uid


def test_upsert_oauth_user_creates_then_matches(require_db: None) -> None:
    from app.db.session import get_sessionmaker
    from app.services.auth import upsert_oauth_user

    subject = uuid4().hex
    email = f"{uuid4().hex}@gmail.com"
    with get_sessionmaker()() as db:
        first = upsert_oauth_user(
            db, provider="google", subject=subject, email=email, full_name="Jane"
        )
        first_id = first.id
        # Same identity again → same user (no duplicate).
        again = upsert_oauth_user(
            db, provider="google", subject=subject, email=email, full_name="Jane"
        )
        assert again.id == first_id
        assert isinstance(first_id, UUID)
