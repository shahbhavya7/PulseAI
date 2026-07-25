"""Pure tests: theme aggregation and embed-on-write behaviour.

No DB or OpenAI: issues are passed in directly and the vector store is faked.
Covers services/insights.py and the embed helper in services/pipeline.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.services.insights import aggregate_themes
from app.services.llm import LLMCallError
from app.services.pipeline import _embed_issues

USER = uuid4()


def _issue(themes: list[str], desc: str) -> Issue:
    # SimpleNamespace is enough — aggregate_themes only reads .themes/.description/.title.
    return cast(Issue, SimpleNamespace(themes=themes, description=desc, title=desc))


def test_themes_ranked_by_count() -> None:
    # Neutral labels that don't hit the synonym map, so this tests ranking only.
    issues = [
        _issue(["missing order"], "order never arrived"),
        _issue(["missing order"], "package lost"),
        _issue(["wrong item shipped"], "got the wrong product"),
    ]
    result = aggregate_themes(cast(Session, None), USER, issues=issues, vector_store=None)
    assert result[0].theme == "missing order" and result[0].count == 2
    assert {t.theme for t in result} == {"missing order", "wrong item shipped"}


def test_synonym_variants_fold_to_one_canonical_theme() -> None:
    # Different phrasings of the same problem must aggregate into one theme, so
    # adding more of the same complaint grows a single bar on the dashboard.
    issues = [
        _issue(["account access"], "can't log in"),
        _issue(["login failure"], "sign-in rejected"),
        _issue(["login-page error"], "password not accepted"),
        _issue(["locked out of account"], "cannot access account"),
    ]
    result = aggregate_themes(cast(Session, None), USER, issues=issues, vector_store=None)
    assert len(result) == 1
    assert result[0].theme == "account access" and result[0].count == 4


def test_near_identical_themes_are_merged() -> None:
    issues = [
        _issue(["photo-upload crash"], "crash on upload"),
        _issue(["photo upload crashes"], "upload crashes"),
        _issue(["Photo-Upload Crash"], "another upload crash"),
    ]
    result = aggregate_themes(cast(Session, None), USER, issues=issues, vector_store=None)
    # All three near-identical labels collapse into one theme with count 3.
    assert len(result) == 1
    assert result[0].count == 3


def test_examples_fall_back_to_member_quotes_without_vector_store() -> None:
    issues = [_issue(["slow checkout"], "checkout takes 30 seconds")]
    result = aggregate_themes(cast(Session, None), USER, issues=issues, vector_store=None)
    assert result[0].examples == ["checkout takes 30 seconds"]


def test_limit_caps_number_of_themes() -> None:
    # Clearly-distinct labels so none merge as near-identical.
    words = [
        "login",
        "billing",
        "search",
        "notifications",
        "onboarding",
        "exports",
        "permissions",
        "uploads",
        "latency",
        "translations",
        "webhooks",
        "analytics",
    ]
    issues = [_issue([f"{w} problem"], f"desc {w}") for w in words]
    result = aggregate_themes(cast(Session, None), USER, issues=issues, vector_store=None, limit=5)
    assert len(result) == 5


# ---- embed-on-write ---------------------------------------------------------


class _FakeStore:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _ in texts]

    def embed_one(self, text: str) -> list[float]:
        return [0.01] * 1536


class _FailingStore:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise LLMCallError("boom")

    def embed_one(self, text: str) -> list[float]:
        raise LLMCallError("boom")


def test_embed_on_write_sets_vector() -> None:
    issue = Issue(description="the app crashes on login")
    _embed_issues(_FakeStore(), [issue])
    assert issue.embedding is not None
    assert len(issue.embedding) == 1536
    assert issue.needs_reembed is False


def test_embed_failure_marks_reembed_not_lost() -> None:
    issue = Issue(description="the app crashes on login")
    _embed_issues(_FailingStore(), [issue])
    # The row is kept (still an Issue), just flagged to retry later.
    assert issue.embedding is None
    assert issue.needs_reembed is True
