"""Cache-aside helper."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from core.metrics import GLOBAL_METRICS
from modules.cache.base import CacheBackend

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Sentinel so a legitimately-None result (e.g. "no eval results yet") is
# distinguishable from a cache miss and doesn't hammer the DB on every request.
_CACHED_NONE = "__traceflow:cached_none__"


def cache_aside(
    backend: CacheBackend,
    key: str,
    compute: Callable[[], T],
    *,
    ttl_s: int | None = None,
) -> T:
    """Return cached value or compute(); record hit/miss in GLOBAL_METRICS.

    Cache read and write failures are caught and logged — the request always
    succeeds, just slower.  The cache is an optimisation, not the source of truth.
    """
    try:
        raw = backend.get(key)
    except Exception:
        logger.warning(
            "cache.get() failed for key=%r — falling back to compute()", key, exc_info=True
        )
        raw = None

    if raw is not None:
        GLOBAL_METRICS.record_cache(True)
        return None if raw == _CACHED_NONE else raw  # type: ignore[return-value]

    GLOBAL_METRICS.record_cache(False)
    out = compute()

    try:
        stored = _CACHED_NONE if out is None else out
        backend.set(key, stored, ttl_s=ttl_s)
    except Exception:
        logger.warning(
            "cache.set() failed for key=%r — value will not be cached", key, exc_info=True
        )

    return out
