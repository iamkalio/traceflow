"""
Cache-aside helpers. Keys and invalidation policy: ``keys.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from modules.cache.base import CacheBackend

T = TypeVar("T")


def cache_aside(
    backend: CacheBackend,
    key: str,
    compute: Callable[[], T],
    *,
    ttl_s: int | None = None,
) -> T:
    """
    Return cached value or ``compute()``; record cache hit/miss via ``core.metrics``.

    Convention: ``None`` from ``get`` means miss (do not store legitimate ``None`` without a wrapper).
    """
    raw = backend.get(key)
    if raw is not None:
        try:
            from core.metrics import GLOBAL_METRICS

            GLOBAL_METRICS.record_cache(True)
        except ImportError:
            pass
        return raw  # type: ignore[return-value]
    try:
        from core.metrics import GLOBAL_METRICS

        GLOBAL_METRICS.record_cache(False)
    except ImportError:
        pass
    out = compute()
    backend.set(key, out, ttl_s=ttl_s)
    return out
