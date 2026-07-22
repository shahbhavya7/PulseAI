"""Redis client factory and a lightweight health probe.

The client is created lazily and cached for the process. ``decode_responses``
is enabled so callers get ``str`` values rather than ``bytes``.
"""

from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    """Return the process-wide cached Redis client."""
    settings = get_settings()
    logger.debug("Creating Redis client")
    return redis.Redis.from_url(
        str(settings.redis_url),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def ping_redis() -> bool:
    """Return True if Redis responds to PING, False on any error.

    Never raises — intended for use in readiness checks where a failure must
    degrade the response rather than crash the request.
    """
    try:
        return bool(get_redis().ping())
    except Exception as exc:  # noqa: BLE001 — health probe must not propagate
        logger.warning("Redis ping failed: %s", exc)
        return False
