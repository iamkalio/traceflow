"""Cache abstraction — memory in dev/tests, Redis in production.

Public API
----------
    from modules.cache import get_cache

    cache = get_cache()          # returns the process-level singleton
    cache.get(key)
    cache.set(key, value, ttl_s=30)
    cache.delete(key)

Backend selection
-----------------
The backend is chosen once at first call to ``get_cache()`` and reused for
the lifetime of the process.  Selection logic:

    CACHE_BACKEND=redis   → RedisCache (REDIS_CACHE_URL or REDIS_URL)
    anything else         → InMemoryCache  (default for local dev + tests)

Environment variables
---------------------
    CACHE_BACKEND      "redis" to enable RedisCache; omit for InMemoryCache
    REDIS_CACHE_URL    Redis URL for cache traffic (optional; falls back to
                       REDIS_URL if not set, to avoid needing a second Redis)

Keeping cache and job-queue on the same Redis is fine for development.
In production, use separate Redis instances (or separate DB indexes, e.g.
redis://host:6379/0 for jobs, redis://host:6379/1 for cache) so that cache
evictions do not interfere with RQ job storage.

Test isolation
--------------
Tests that need a clean cache should use the ``fresh_cache`` pytest fixture
defined in ``tests/conftest.py``.  That fixture monkeypatches
``_cache_instance`` to a fresh InMemoryCache before each test and calls
``clear()`` after, so no state leaks between test cases.
"""

from __future__ import annotations

import os

from modules.cache.base import CacheBackend
from modules.cache.memory import InMemoryCache

# The process-level singleton.  None until first call to get_cache().
_cache_instance: CacheBackend | None = None


def get_cache() -> CacheBackend:
    """Return the process-level cache singleton, building it on first call.

    Thread-safe enough for our use case: in the worst case two threads both
    see ``_cache_instance is None`` and both call ``_build_cache()``.  The
    second assignment wins, and both workers end up pointing at the same type
    of backend.  For InMemoryCache this wastes one object; for RedisCache both
    objects share the same server-side state anyway.  A lock is not worth the
    added complexity here.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = _build_cache()
    return _cache_instance


def _build_cache() -> CacheBackend:
    """Instantiate the correct backend based on environment variables."""
    backend_name = os.environ.get("CACHE_BACKEND", "memory").lower().strip()

    if backend_name == "redis":
        # Import here (not at module top) so that importing modules.cache
        # in tests does not require redis-py to be importable.
        from modules.cache.redis import RedisCache
        from core.config import redis_url

        # Allow a separate Redis URL for cache traffic so that cache evictions
        # don't interfere with RQ job storage on a shared Redis.
        url = os.environ.get("REDIS_CACHE_URL") or redis_url()
        return RedisCache(url)

    # Default: in-memory.  Works for single-process dev and all unit tests.
    return InMemoryCache()


def _reset_cache() -> None:
    """Tear down the singleton so the next call to get_cache() rebuilds it.

    Only for test use.  Calling this in production code will cause the next
    request to rebuild the backend, losing all cached data.
    """
    global _cache_instance
    _cache_instance = None
