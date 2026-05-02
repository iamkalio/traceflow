"""Unit tests for the cache_aside() decorator helper.

Run with:
    cd backend && python -m pytest tests/unit/cache/test_decorators.py -v

These tests verify the contract of cache_aside() against InMemoryCache.
They do NOT test Redis, FastAPI, or the DB — just the caching logic itself.

Key behaviours under test:
  1. Hit  — second call returns cached value; compute() not called again.
  2. Miss — first call calls compute() and stores result.
  3. Expiry — after TTL, compute() is called again.
  4. Invalidation — after delete(), compute() is called again.
  5. None caching — compute() returning None is cached (no repeated DB hits).
  6. Empty list caching — [] is cached and not treated as a miss.
  7. Graceful degradation — broken backend falls through to compute().
  8. Metrics — hits and misses are recorded in GLOBAL_METRICS.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from core.metrics import GLOBAL_METRICS
from modules.cache.decorators import cache_aside
from modules.cache.memory import InMemoryCache


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _counter_compute(values: list):
    """Return a compute callable that pops from a list.

    Each call to the returned function returns the next item.  If compute()
    is called more times than expected, the list is exhausted and IndexError
    is raised — which makes the test fail loudly instead of silently.
    """
    def _compute():
        return values.pop(0)
    return _compute


# ------------------------------------------------------------------
# 1. Cache hit behaviour
# ------------------------------------------------------------------

def test_second_call_returns_cached_value():
    """compute() is called exactly once; the second call returns the cached result."""
    cache = InMemoryCache()
    call_count = 0

    def compute():
        nonlocal call_count
        call_count += 1
        return {"data": "hello"}

    r1 = cache_aside(cache, "k", compute, ttl_s=60)
    r2 = cache_aside(cache, "k", compute, ttl_s=60)

    assert r1 == r2 == {"data": "hello"}
    assert call_count == 1  # must only call compute once


def test_third_call_still_uses_cache():
    """Repeated calls all hit the cache without re-computing."""
    cache = InMemoryCache()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return 42

    for _ in range(5):
        assert cache_aside(cache, "k", compute, ttl_s=60) == 42

    assert calls == 1


# ------------------------------------------------------------------
# 2. Cache miss behaviour
# ------------------------------------------------------------------

def test_first_call_populates_cache():
    """On first call, compute() runs and the result is stored in the cache."""
    cache = InMemoryCache()
    cache_aside(cache, "k", lambda: "value", ttl_s=60)
    # The cache should now have the value stored directly.
    assert cache.get("k") == "value"


def test_different_keys_have_independent_compute():
    """Two different keys each invoke their own compute function."""
    cache = InMemoryCache()
    a_calls, b_calls = 0, 0

    def compute_a():
        nonlocal a_calls
        a_calls += 1
        return "A"

    def compute_b():
        nonlocal b_calls
        b_calls += 1
        return "B"

    assert cache_aside(cache, "key:a", compute_a, ttl_s=60) == "A"
    assert cache_aside(cache, "key:b", compute_b, ttl_s=60) == "B"
    assert a_calls == 1
    assert b_calls == 1


# ------------------------------------------------------------------
# 3. Expiry
# ------------------------------------------------------------------

def test_expired_entry_triggers_recompute():
    """After TTL elapses, compute() is called again for fresh data."""
    cache = InMemoryCache()
    values = ["fresh_v1", "fresh_v2"]

    r1 = cache_aside(cache, "k", _counter_compute(values[:1] + ["fresh_v2"]), ttl_s=1)
    assert r1 == "fresh_v1"

    time.sleep(1.1)  # let TTL expire

    # After expiry, compute is called again with the second value.
    values = ["fresh_v2"]
    r2 = cache_aside(cache, "k", _counter_compute(values), ttl_s=1)
    assert r2 == "fresh_v2"


# ------------------------------------------------------------------
# 4. Invalidation
# ------------------------------------------------------------------

def test_delete_causes_recompute_on_next_call():
    """After a cache.delete(), the next cache_aside call re-runs compute()."""
    cache = InMemoryCache()
    call_count = 0

    def compute():
        nonlocal call_count
        call_count += 1
        return f"v{call_count}"

    r1 = cache_aside(cache, "k", compute, ttl_s=60)
    assert r1 == "v1"
    assert call_count == 1

    # Simulate a write-path cache invalidation.
    cache.delete("k")

    r2 = cache_aside(cache, "k", compute, ttl_s=60)
    assert r2 == "v2"
    assert call_count == 2  # re-computed after invalidation


# ------------------------------------------------------------------
# 5. None caching  ← THIS IS THE BUG FIX
# ------------------------------------------------------------------

def test_none_result_is_cached_not_refetched():
    """compute() returning None is stored and not re-called on the next hit.

    This is the bug that existed in the original code: if compute() returns
    None, cache.get() would also return None, which is indistinguishable from
    a cache miss.  cache_aside would call compute() on every request.

    The fix: store a sentinel string (_CACHED_NONE) so that the next
    cache.get() returns a non-None value, and cache_aside unwraps it back to
    None for the caller.
    """
    cache = InMemoryCache()
    call_count = 0

    def compute():
        nonlocal call_count
        call_count += 1
        return None  # legitimate "no result" from DB

    r1 = cache_aside(cache, "k", compute, ttl_s=60)
    r2 = cache_aside(cache, "k", compute, ttl_s=60)

    assert r1 is None
    assert r2 is None
    assert call_count == 1  # None was cached; compute only ran once


def test_none_result_stored_as_sentinel_in_cache():
    """The internal storage uses the sentinel, not literal None."""
    from modules.cache.decorators import _CACHED_NONE

    cache = InMemoryCache()
    cache_aside(cache, "k", lambda: None, ttl_s=60)

    # Internally, the cache stores the sentinel string, not None.
    assert cache.get("k") == _CACHED_NONE


# ------------------------------------------------------------------
# 6. Empty list caching
# ------------------------------------------------------------------

def test_empty_list_is_cached():
    """An empty list is cached and does not cause repeated DB hits.

    The trace evals endpoint returns [] when no evals have run yet.
    Without caching [], every page view would hit the DB.
    """
    cache = InMemoryCache()
    call_count = 0

    def compute():
        nonlocal call_count
        call_count += 1
        return []

    r1 = cache_aside(cache, "k", compute, ttl_s=60)
    r2 = cache_aside(cache, "k", compute, ttl_s=60)

    assert r1 == r2 == []
    assert call_count == 1


def test_empty_dict_is_cached():
    """An empty dict is also a legitimate cacheable value."""
    cache = InMemoryCache()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {}

    cache_aside(cache, "k", compute, ttl_s=60)
    cache_aside(cache, "k", compute, ttl_s=60)
    assert calls == 1


# ------------------------------------------------------------------
# 7. Graceful degradation
# ------------------------------------------------------------------

def test_broken_backend_get_falls_through_to_compute():
    """If cache.get() raises, cache_aside logs a warning and calls compute().

    The request must succeed — a broken cache must never cause a 500.

    We also assert that set() was still attempted after the get failure.
    This is important: cache_aside should try to write the computed value
    even when the read failed, so that if Redis recovers mid-request the
    next caller can benefit from a warm cache.
    """
    broken = MagicMock()
    broken.get.side_effect = ConnectionError("Redis is down")
    # set succeeds (partial failure: read broken, write ok — possible during
    # a failover where a new Redis primary just came up).
    broken.set.side_effect = None

    result = cache_aside(broken, "k", lambda: "from_db", ttl_s=60)

    assert result == "from_db"
    broken.get.assert_called_once_with("k")
    # Even though get() raised, cache_aside must still attempt set() so
    # that subsequent callers can benefit if the backend recovered.
    broken.set.assert_called_once_with("k", "from_db", ttl_s=60)


def test_broken_backend_set_still_returns_computed_value():
    """If cache.set() raises, the computed value is still returned to the caller."""
    broken = MagicMock()
    broken.get.return_value = None  # cache miss
    broken.set.side_effect = ConnectionError("Redis is down")

    result = cache_aside(broken, "k", lambda: "from_db", ttl_s=60)

    assert result == "from_db"
    # Verify set() was called with the exact right arguments.
    # assert_called_once() alone would pass even if the key or value were wrong.
    broken.set.assert_called_once_with("k", "from_db", ttl_s=60)


def test_broken_backend_does_not_raise_to_caller():
    """Neither get nor set exceptions should propagate out of cache_aside."""
    broken = MagicMock()
    broken.get.side_effect = RuntimeError("unexpected")
    broken.set.side_effect = RuntimeError("unexpected")

    # Should not raise
    result = cache_aside(broken, "k", lambda: 99, ttl_s=60)
    assert result == 99


def test_persistently_broken_backend_every_call_goes_to_compute():
    """When the backend is permanently broken, every call must still go to
    compute() and return the correct value.

    This is the full non-blocking guarantee: the cache being completely down
    is equivalent to it not existing at all.  Every request succeeds, just
    without the performance benefit.

    This test is the unit-level counterpart of the integration test
    test_broken_cache_falls_back_to_db_on_every_request in test_query_cache.py.
    Together they cover both the building block (this test) and the full HTTP
    request pipeline (the integration test).
    """
    broken = MagicMock()
    broken.get.side_effect = ConnectionError("Redis is down")
    broken.set.side_effect = ConnectionError("Redis is down")

    call_count = 0

    def compute():
        nonlocal call_count
        call_count += 1
        return f"db_result_{call_count}"

    # Simulate three consecutive requests with a broken cache.
    r1 = cache_aside(broken, "k", compute, ttl_s=60)
    r2 = cache_aside(broken, "k", compute, ttl_s=60)
    r3 = cache_aside(broken, "k", compute, ttl_s=60)

    # Every call returns the correct value.
    assert r1 == "db_result_1"
    assert r2 == "db_result_2"
    assert r3 == "db_result_3"

    # Every call went to compute because nothing could be cached.
    assert call_count == 3


# ------------------------------------------------------------------
# 8. Metrics recording
# ------------------------------------------------------------------

def test_cache_hit_increments_hit_counter():
    """A cache hit increments GLOBAL_METRICS.cache_hits."""
    cache = InMemoryCache()
    cache_aside(cache, "k", lambda: "v", ttl_s=60)  # miss — populates cache

    hits_before = GLOBAL_METRICS.cache_hits
    cache_aside(cache, "k", lambda: "v", ttl_s=60)  # hit
    assert GLOBAL_METRICS.cache_hits == hits_before + 1


def test_cache_miss_increments_miss_counter():
    """A cache miss increments GLOBAL_METRICS.cache_misses."""
    cache = InMemoryCache()

    misses_before = GLOBAL_METRICS.cache_misses
    cache_aside(cache, "fresh_key_xyz", lambda: "v", ttl_s=60)  # miss
    assert GLOBAL_METRICS.cache_misses == misses_before + 1
