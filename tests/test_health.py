"""Tests for the liveness and readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.services import health as health_service


def test_health_ok(client: TestClient) -> None:
    """/health returns 200 and reports the service identity."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "PulseAI"
    assert body["version"] == __version__


def test_ready_all_up(client: TestClient, monkeypatch: object) -> None:
    """/ready returns 200 when every dependency probe passes."""
    monkeypatch.setattr(health_service, "ping_db", lambda: True)  # type: ignore[attr-defined]
    monkeypatch.setattr(health_service, "ping_redis", lambda: True)  # type: ignore[attr-defined]

    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert {d["name"] for d in body["dependencies"]} == {"database", "redis"}
    assert all(d["ok"] for d in body["dependencies"])


def test_ready_degrades_to_503(client: TestClient, monkeypatch: object) -> None:
    """/ready degrades to 503 (never crashes) when a dependency is down."""
    monkeypatch.setattr(health_service, "ping_db", lambda: False)  # type: ignore[attr-defined]
    monkeypatch.setattr(health_service, "ping_redis", lambda: True)  # type: ignore[attr-defined]

    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    db_dep = next(d for d in body["dependencies"] if d["name"] == "database")
    assert db_dep["ok"] is False
