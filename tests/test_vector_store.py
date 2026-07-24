"""Tests for the OpenAI-backed VectorStore (fake client, no real API)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import vector_store as vs
from app.services.llm import LLMCallError, LLMConfigError
from app.services.vector_store import OpenAIVectorStore


def _fake_client(dim: int) -> Any:
    def create(*, model: str, input: list[str]) -> Any:
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * dim) for _ in input])

    return SimpleNamespace(embeddings=SimpleNamespace(create=create))


def test_embed_returns_one_vector_per_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vs, "get_openai_client", lambda: _fake_client(1536))
    vectors = OpenAIVectorStore().embed(["a", "b"])
    assert len(vectors) == 2 and all(len(v) == 1536 for v in vectors)


def test_embed_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vs, "get_openai_client", lambda: _fake_client(1536))
    assert len(OpenAIVectorStore().embed_one("hello")) == 1536


def test_empty_input_returns_empty_without_calling_api() -> None:
    assert OpenAIVectorStore().embed([]) == []


def test_dimension_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vs, "get_openai_client", lambda: _fake_client(512))
    with pytest.raises(LLMCallError):
        OpenAIVectorStore().embed(["a"])


def test_missing_key_propagates_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise LLMConfigError("no key")

    monkeypatch.setattr(vs, "get_openai_client", boom)
    with pytest.raises(LLMConfigError):
        OpenAIVectorStore().embed(["a"])
