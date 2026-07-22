"""Application logging configuration.

A single :func:`configure_logging` call sets up the root logger with a concise,
consistent format. It is idempotent so repeated calls (e.g. in tests) do not
stack handlers.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once.

    Args:
        level: Log level name (e.g. ``"INFO"``, ``"DEBUG"``). Invalid names
            fall back to ``INFO``.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)

    # Tame noisy third-party loggers while keeping our own at the chosen level.
    logging.getLogger("uvicorn.access").setLevel(max(resolved, logging.INFO))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; a thin wrapper for import consistency."""
    return logging.getLogger(name)
