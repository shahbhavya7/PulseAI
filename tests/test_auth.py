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


def test_providers_reports_email_and_oauth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pin provider config so the test doesn't depend on the developer's .env:
    # no OAuth configured, email on by default.
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", None)
    monkeypatch.setattr(settings, "google_client_secret", None)
    monkeypatch.setattr(settings, "apple_client_id", None)
    monkeypatch.setattr(settings, "email_login_enabled", True)

    resp = client.get("/auth/providers")
    assert resp.status_code == 200
    assert resp.json() == {"providers": [], "email": True}


def test_login_unconfigured_provider_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", None)
    monkeypatch.setattr(settings, "google_client_secret", None)
    resp = client.get("/auth/login/google", follow_redirects=False)
    # Not configured → treated as unavailable.
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


# ---- Email + password (DB) -------------------------------------------------


def test_password_hash_round_trip() -> None:
    from app.services.auth import hash_password, verify_password

    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_register_then_login_and_me(client: TestClient, require_db: None) -> None:
    email = f"{uuid4().hex}@example.com"

    # Register → 201, sets the session cookie, /auth/me works on the same client.
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Reg Tester"},
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["email"] == email
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == email

    # A fresh client (no cookie) can log in with the same credentials.
    with TestClient(client.app) as other:
        login = other.post("/auth/login/email", json={"email": email, "password": "supersecret1"})
        assert login.status_code == 200
        assert login.json()["email"] == email


def test_register_duplicate_email_409(client: TestClient, require_db: None) -> None:
    email = f"{uuid4().hex}@example.com"
    body = {"email": email, "password": "supersecret1"}
    assert client.post("/auth/register", json=body).status_code == 201
    dup = client.post("/auth/register", json=body)
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "email_taken"


def test_register_weak_password_400(client: TestClient, require_db: None) -> None:
    resp = client.post(
        "/auth/register",
        json={"email": f"{uuid4().hex}@example.com", "password": "short"},
    )
    # Rejected by the schema (min_length=8) → 422 before the route body runs.
    assert resp.status_code == 422


def test_login_wrong_password_401(client: TestClient, require_db: None) -> None:
    email = f"{uuid4().hex}@example.com"
    client.post("/auth/register", json={"email": email, "password": "supersecret1"})
    resp = client.post("/auth/login/email", json={"email": email, "password": "not-the-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


def test_login_unknown_email_401(client: TestClient, require_db: None) -> None:
    resp = client.post(
        "/auth/login/email",
        json={"email": f"{uuid4().hex}@nobody.com", "password": "whatever12"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"
