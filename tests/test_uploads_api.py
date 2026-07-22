"""Integration tests for POST /uploads (require a live Postgres).

Content is made unique per run with ``uuid4`` so persisted rows from earlier
runs don't dedup these away.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("require_db")


def _csv(*rows: str, header: str = "text") -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def test_upload_csv_creates_tickets(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(f"Login page throws an error {marker}", f"Checkout is very slow {marker}")
    resp = client.post("/uploads", files={"file": ("issues.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parser"] == "csv"
    assert body["counts"]["created"] == 2
    assert len(body["created_items"]) == 2
    assert body["created_items"][0]["ticket_id"] and body["created_items"][0]["issue_id"]


def test_upload_counts_blanks_and_duplicates(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(
        f"Unique complaint {marker}",
        "",  # blank row
        f"unique   complaint   {marker}",  # duplicate after normalisation
    )
    resp = client.post("/uploads", files={"file": ("mix.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    counts = resp.json()["counts"]
    assert counts["created"] == 1 and counts["blanks"] == 1 and counts["duplicates"] == 1


def test_upload_redacts_pii_before_storage(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(f"Email me at user@example.com about {marker}")
    resp = client.post("/uploads", files={"file": ("pii.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    assert "pii_redacted" in resp.json()["created_items"][0]["flags"]


def test_upload_missing_text_column_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/uploads",
        files={"file": ("bad.csv", b"id,priority\n1,high\n2,low\n", "text/csv")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "missing_text_column"


def test_upload_dedup_across_two_uploads(client: TestClient) -> None:
    marker = uuid4().hex
    data = _csv(f"Repeated across uploads {marker}")
    first = client.post("/uploads", files={"file": ("a.csv", data, "text/csv")})
    assert first.json()["counts"]["created"] == 1
    second = client.post("/uploads", files={"file": ("b.csv", data, "text/csv")})
    assert second.status_code == 201
    counts = second.json()["counts"]
    assert counts["created"] == 0 and counts["duplicates"] == 1


def test_upload_text_file_boundary_split(client: TestClient) -> None:
    marker = uuid4().hex
    blob = (
        f"From: alice@example.com\nOrder {marker} never arrived.\n"
        f"From: bob@example.com\nWrong item {marker} shipped."
    ).encode()
    resp = client.post("/uploads", files={"file": ("thread.txt", blob, "text/plain")})
    assert resp.status_code == 201, resp.text
    assert resp.json()["counts"]["created"] == 2


def test_malformed_user_id_header_returns_400(client: TestClient) -> None:
    resp = client.post(
        "/uploads",
        files={"file": ("x.csv", _csv("anything"), "text/csv")},
        headers={"X-User-Id": "not-a-uuid"},
    )
    assert resp.status_code == 400
