"""Cache-aside helper.

The cache-aside pattern in one sentence:
    "Check the cache first. On miss, compute the real value, store it,
    and return it.  The cache is always populated lazily — never eagerly."

This file contains one public function: ``cache_aside()``.  Everything else
is an implementation detail.

Key design decisions explained inline below.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from core.metrics import GLOBAL_METRICS
from modules.cache.base import CacheBackend

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ------------------------------------------------------------------
# None sentinel
# ------------------------------------------------------------------
# Problem: cache.get(key) returning None means two different things:
#   1. "Key does not exist in the cache" (cache miss)
#   2. "Key exists and its value is the Python None object"
#
# Without a sentinel, case 2 is indistinguishable from case 1, so a
# legitimate None result from compute() would never be cached.  Every
# request would miss, call compute(), and hammer the DB — even when the
# "there are no results" answer is perfectly correct and stable.
#
# The fix: store this sentinel string instead of None.  The sentinel is
# chosen to be:
#   - A string (JSON-safe for Redis)
#   - Unlikely to be confused with real data
#   - Human-readable if you inspect Redis with redis-cli
# ------------------------------------------------------------------
_CACHED_NONE = "__traceflow:cached_none__"


def cache_aside(
    backend: CacheBackend,
    key: str,
    compute: Callable[[], T],
    *,
    ttl_s: int | None = None,
) -> T:
    """Return cached value or compute(); record hit/miss in GLOBAL_METRICS.

    Graceful degradation
    --------------------
    Both the cache read and the cache write are wrapped in try/except.
    If the cache backend raises (e.g. Redis is down, network timeout,
    serialisation error), the function logs a warning and continues:
      - On read failure  → falls through to compute() as if it were a miss.
      - On write failure → the computed value is still returned to the caller;
                          the entry just won't be cached for next time.
    The caller (your FastAPI route handler) never sees a cache exception.
    The request succeeds, just slower.  This is the correct behaviour: the
    cache is an optimisation, not the source of truth.

    None caching
    ------------
    If compute() returns None (e.g. a trace with no eval results yet), we
    store ``_CACHED_NONE`` and return None to the caller.  On subsequent
    reads the sentinel is unwrapped back to None.  This prevents the DB
    from being hit on every request for a legitimately-empty result.

    Metrics
    -------
    Every call records either a hit or a miss in GLOBAL_METRICS so that
    the hit rate is always observable via the /metrics endpoint.
    """

    # ------------------------------------------------------------------
    # Step 1 — Attempt a cache read
    # ------------------------------------------------------------------
    # We wrap in try/except so that a broken Redis connection does not
    # propagate up to the request handler as a 500 error.
    try:
        raw = backend.get(key)
    except Exception:
        logger.warning(
            "cache.get() failed for key=%r — falling back to compute()", key, exc_info=True
        )
        raw = None  # treat as a miss and let compute() run

    if raw is not None:
        # Cache hit.  Unwrap the None sentinel if that is what was stored.
        GLOBAL_METRICS.record_cache(True)
        return None if raw == _CACHED_NONE else raw  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Step 2 — Cache miss: run the real computation
    # ------------------------------------------------------------------
    GLOBAL_METRICS.record_cache(False)
    out = compute()

    # ------------------------------------------------------------------
    # Step 3 — Best-effort cache write
    # ------------------------------------------------------------------
    # We wrap in try/except for the same reason as the read: a write
    # failure should degrade silently, not crash the request.
    try:
        # Store the sentinel for None results so future reads are hits.
        stored = _CACHED_NONE if out is None else out
        backend.set(key, stored, ttl_s=ttl_s)
    except Exception:
        logger.warning(
            "cache.set() failed for key=%r — value will not be cached", key, exc_info=True
        )

    return out
