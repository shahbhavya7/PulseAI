"""VectorStore interface and the OpenAI embedding implementation.

Embeddings turn cleaned issue text into a 1536-dim vector we store in the
pgvector ``embedding`` column. Callers depend on the :class:`VectorStore`
Protocol, not on OpenAI directly, so tests inject a fake embedder and the model
can be swapped in one place.

Failures raise the same :class:`~app.services.llm.LLMError` family the rest of
the AI code uses, so the persist flow can catch them and mark a row for re-embed
instead of losing it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import openai

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.issue import EMBEDDING_DIM
from app.services.llm import LLMCallError, get_openai_client

logger = get_logger(__name__)


class VectorStore(Protocol):
    """Anything that can turn texts into embedding vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text (order preserved)."""
        ...

    def embed_one(self, text: str) -> list[float]:
        """Return a single vector for ``text``."""
        ...


class OpenAIVectorStore:
    """:class:`VectorStore` backed by OpenAI's embeddings API."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or get_settings().openai_embedding_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = get_openai_client()  # LLMConfigError (no key) propagates as-is
        try:
            response = client.embeddings.create(model=self._model, input=texts)
        except openai.APIError as exc:
            logger.warning("Embedding API error: %s", exc)
            raise LLMCallError(f"Embedding service error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 — never crash on an embed failure
            logger.exception("Unexpected embedding failure")
            raise LLMCallError(f"Unexpected embedding failure: {exc}") from exc

        vectors = [item.embedding for item in response.data]
        if any(len(v) != EMBEDDING_DIM for v in vectors):
            raise LLMCallError(f"Embedding dimension mismatch (expected {EMBEDDING_DIM}).")
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_vector_store() -> OpenAIVectorStore:
    """Return the process-wide default vector store."""
    return OpenAIVectorStore()
