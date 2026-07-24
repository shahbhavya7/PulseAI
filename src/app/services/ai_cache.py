"""Redis cache for AI analysis results, keyed by ``content_hash``.

Identical ticket text (same user-scoped ``content_hash``) returns the identical
stored analysis — cheaper and guarantees consistency across runs. The cache is
best-effort: if Redis is down, reads miss and writes are dropped, and the
pipeline just calls the model. It never raises.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.schemas.ai import TicketAnalysis

logger = get_logger(__name__)

_KEY_PREFIX = "pulse:ai:analysis:"


def _key(content_hash: str) -> str:
    return f"{_KEY_PREFIX}{content_hash}"


def get_cached_analysis(content_hash: str) -> TicketAnalysis | None:
    """Return the cached analysis for ``content_hash``, or None on miss/error."""
    try:
        raw = get_redis().get(_key(content_hash))
    except Exception as exc:  # noqa: BLE001 — cache must never break the request
        logger.warning("AI cache read failed: %s", exc)
        return None
    if raw is None:
        return None
    try:
        return TicketAnalysis.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001 — treat corrupt cache as a miss
        logger.warning("Discarding unparseable cached analysis: %s", exc)
        return None


def set_cached_analysis(content_hash: str, analysis: TicketAnalysis) -> None:
    """Store ``analysis`` under ``content_hash`` with the configured TTL."""
    ttl = get_settings().ai_cache_ttl_seconds
    try:
        get_redis().set(_key(content_hash), analysis.model_dump_json(), ex=ttl)
    except Exception as exc:  # noqa: BLE001 — a failed write just means a miss later
        logger.warning("AI cache write failed: %s", exc)
