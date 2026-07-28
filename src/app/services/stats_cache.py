"""Redis cache for the Overview dashboard aggregates (``GET /stats``).

Computing stats is a handful of ``GROUP BY`` queries plus theme aggregation.
Cheap once, wasteful on every page view — and the Overview is the page users
click back to constantly, flipping between weeks. Each ``(user, filters)``
combination is cached under a per-user key prefix.

**Invalidation is explicit, not TTL-driven.** Anything that changes a user's
issues (an upload, an analysis, a ticket deletion) calls
:func:`invalidate_user_stats`, which drops every cached view for that user in
one pass. A TTL alone would show a stale Overview for its duration right after
an upload, which is exactly when the user is looking at it. The TTL that does
exist is only a backstop against leaked keys.

Over-invalidation is deliberate: adding a W31 issue also clears the cached W30
view. Precise per-week invalidation would still have to clear the all-time view
and the cross-week ``weekly_severity`` series anyway, so the extra bookkeeping
buys nothing but more ways to serve a wrong number.

Best-effort throughout: if Redis is down, reads miss, writes drop, and the
request just recomputes from Postgres. It never raises.
"""

from __future__ import annotations

import hashlib

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.schemas.stats import StatsResponse

logger = get_logger(__name__)

_PREFIX = "pulse:stats:"


def _user_prefix(user_id: str) -> str:
    """All cached views for one user share this prefix, so one scan clears them."""
    return f"{_PREFIX}{user_id}:"


def _key(
    user_id: str,
    *,
    week: str | None,
    min_confidence: float | None,
    needs_manual_review: bool | None,
) -> str:
    """Key one cached view.

    The filter combination is hashed rather than interpolated: a raw week string
    is user-controlled input, and a short digest keeps keys fixed-length and
    free of characters that would need escaping.
    """
    conf = min_confidence if min_confidence is not None else "*"
    review = needs_manual_review if needs_manual_review is not None else "*"
    fingerprint = f"{week or '*'}|{conf}|{review}"
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
    return f"{_user_prefix(user_id)}{digest}"


def get_cached_stats(
    user_id: str,
    *,
    week: str | None = None,
    min_confidence: float | None = None,
    needs_manual_review: bool | None = None,
) -> StatsResponse | None:
    """Return the cached stats for this filter combination, or None on miss."""
    try:
        raw = get_redis().get(
            _key(
                user_id,
                week=week,
                min_confidence=min_confidence,
                needs_manual_review=needs_manual_review,
            )
        )
    except Exception as exc:  # noqa: BLE001 — cache must never break the request
        logger.warning("Stats cache read failed: %s", exc)
        return None
    if raw is None:
        return None
    try:
        return StatsResponse.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001 — a stale/renamed schema reads as a miss
        logger.warning("Discarding unparseable cached stats: %s", exc)
        return None


def set_cached_stats(
    user_id: str,
    stats: StatsResponse,
    *,
    week: str | None = None,
    min_confidence: float | None = None,
    needs_manual_review: bool | None = None,
) -> None:
    """Store ``stats`` for this filter combination."""
    ttl = get_settings().stats_cache_ttl_seconds
    try:
        get_redis().set(
            _key(
                user_id,
                week=week,
                min_confidence=min_confidence,
                needs_manual_review=needs_manual_review,
            ),
            stats.model_dump_json(),
            ex=ttl,
        )
    except Exception as exc:  # noqa: BLE001 — a failed write just means a miss later
        logger.warning("Stats cache write failed: %s", exc)


def invalidate_user_stats(user_id: str) -> int:
    """Drop every cached stats view for one user. Returns how many keys went.

    Called after any write that changes the user's issues. Uses ``scan_iter``
    rather than ``KEYS`` so a large keyspace is walked in cursor batches instead
    of blocking Redis on one sweep.
    """
    pattern = f"{_user_prefix(user_id)}*"
    try:
        client = get_redis()
        keys = list(client.scan_iter(match=pattern, count=100))
        if not keys:
            return 0
        client.delete(*keys)
    except Exception as exc:  # noqa: BLE001 — a failed purge must not fail the write
        # Worst case the user sees stale numbers until the TTL backstop expires.
        logger.warning("Stats cache invalidation failed: %s", exc)
        return 0
    logger.info("Invalidated %d cached stats view(s) for user=%s", len(keys), user_id)
    return len(keys)
