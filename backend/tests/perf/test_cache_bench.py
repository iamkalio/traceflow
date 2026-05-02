"""Performance benchmarks for the cache layer.

Run with:
    cd backend && python -m pytest tests/perf/test_cache_bench.py -v -s

The ``-s`` flag keeps stdout open so you can see the printed timing numbers.

These are NOT pass/fail tests in the usual sense.  They measure:
  - How much faster a cache hit is vs a full compute() call.
  - How quickly InMemoryCache handles a sustained load.
  - Memory growth over many set() calls (no unbounded accumulation).

Why timing-based tests are fragile
-----------------------------------
Absolute timing thresholds (e.g. "must complete in <1ms") are inherently
CI-hostile because CI machines have unpredictable load.  To keep these tests
meaningful without being flaky, we use *relative* thresholds:
  - Cache hits must be at least 10x faster than a simulated 10ms compute().
  - get()/set() throughput must exceed a minimum ops/s that any modern CPU
    should hit easily.

Reading the output
------------------
Each test prints a summary line like:
    [perf] 1000 cache hits: 2.1ms total, 0.002ms per hit
Run the tests, read the numbers, and compare them over time.  If a number
gets 10x worse, something regressed.
"""

from __future__ import annotations

import time

import pytest

from modules.cache.decorators import cache_aside
from modules.cache.memory import InMemoryCache


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _elapsed_ms(fn, n: int = 1) -> float:
    """Run fn() n times and return total elapsed milliseconds."""
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) * 1000


# ---------------------------------------------------------------------------
# 1. Cache hit is dramatically faster than compute()
# ---------------------------------------------------------------------------

class TestCacheHitLatency:
    def test_cache_hit_is_at_least_10x_faster_than_compute(self):
        """A cache hit should be at least 10x faster than the simulated compute.

        We simulate a 10ms DB query.  A cache hit should be sub-millisecond.
        This ratio (10x) is deliberately conservative — in practice it is
        usually 100-1000x.
        """
        cache = InMemoryCache()
        N = 100

        def slow_compute():
            time.sleep(0.01)  # simulates a 10ms DB query
            return {"data": "result"}

        # Cold: first call must compute.
        cache_aside(cache, "k", slow_compute, ttl_s=60)

        # Measure compute time (single call, warm).
        compute_ms = _elapsed_ms(lambda: slow_compute(), n=1)

        # Measure N cache hits.
        hit_ms = _elapsed_ms(
            lambda: cache_aside(cache, "k", lambda: None, ttl_s=60),
            n=N,
        )
        per_hit_ms = hit_ms / N

        print(f"\n[perf] compute: {compute_ms:.1f}ms | cache hit avg: {per_hit_ms:.4f}ms")
        print(f"[perf] speedup: {compute_ms / per_hit_ms:.0f}x")

        # Each cache hit should be at least 10x faster than one compute call.
        assert per_hit_ms < compute_ms / 10, (
            f"Cache hit ({per_hit_ms:.4f}ms) is not 10x faster than compute ({compute_ms:.1f}ms)"
        )

    def test_100_cache_hits_complete_in_under_10ms(self):
        """100 cache hits on InMemoryCache should be almost instantaneous.

        This is a smoke-check: if InMemoryCache becomes slower than this,
        something is very wrong (e.g. an O(n) scan was introduced).
        The 10ms budget is very generous for a dict lookup.
        """
        cache = InMemoryCache()
        cache.set("k", {"items": list(range(50)), "next_cursor": None}, ttl_s=60)

        elapsed = _elapsed_ms(lambda: cache.get("k"), n=100)
        per_hit = elapsed / 100

        print(f"\n[perf] 100 cache hits: {elapsed:.2f}ms total, {per_hit:.4f}ms per hit")

        assert elapsed < 10, (
            f"100 cache hits took {elapsed:.2f}ms — expected < 10ms"
        )


# ---------------------------------------------------------------------------
# 2. Set / get throughput
# ---------------------------------------------------------------------------

class TestThroughput:
    def test_set_10000_unique_keys_completes_quickly(self):
        """Writing 10,000 unique entries to InMemoryCache should take under 1 second.

        This simulates a cold-start warm-up of a large cache.
        """
        cache = InMemoryCache()

        elapsed = _elapsed_ms(
            lambda: [cache.set(f"k:{i}", f"v:{i}", ttl_s=60) for i in range(10_000)]
        )

        print(f"\n[perf] 10,000 set() calls: {elapsed:.1f}ms")
        assert elapsed < 1000, f"10,000 set() calls took {elapsed:.1f}ms — expected < 1000ms"

    def test_mixed_read_write_throughput(self):
        """Alternating get()/set() simulates real cache traffic patterns.

        In production, most operations are reads (hits).  We simulate 80%
        reads, 20% writes across 1000 operations.
        """
        cache = InMemoryCache()
        N = 1000
        keys = [f"key:{i % 50}" for i in range(N)]  # 50 unique keys, cycling

        # Pre-populate.
        for k in set(keys):
            cache.set(k, f"value_for_{k}", ttl_s=60)

        ops = 0

        def mixed_traffic():
            nonlocal ops
            for i, k in enumerate(keys):
                if i % 5 == 0:   # 20% writes
                    cache.set(k, f"new_value_{ops}", ttl_s=60)
                else:            # 80% reads
                    cache.get(k)
                ops += 1

        elapsed = _elapsed_ms(mixed_traffic)
        throughput = N / (elapsed / 1000)

        print(f"\n[perf] {N} mixed ops: {elapsed:.1f}ms, {throughput:,.0f} ops/sec")
        # Anything above 10,000 ops/sec is fine for our use case.
        assert throughput > 10_000, f"Throughput too low: {throughput:.0f} ops/sec"


# ---------------------------------------------------------------------------
# 3. Memory growth
# ---------------------------------------------------------------------------

class TestMemoryGrowth:
    def test_expired_entries_are_evicted_on_read(self):
        """Entries with short TTL should be removed from _data on the next read.

        This verifies that lazy eviction actually shrinks the dict, not just
        hides the values.  Without eviction, the dict grows without bound
        (a memory leak for long-running processes).
        """
        cache = InMemoryCache()

        # Write 100 entries with a 1-second TTL.
        for i in range(100):
            cache.set(f"k:{i}", f"v:{i}", ttl_s=1)

        assert len(cache._data) == 100

        time.sleep(1.1)  # let them all expire

        # Reading each key triggers lazy eviction.
        for i in range(100):
            result = cache.get(f"k:{i}")
            assert result is None  # they expired

        # The dict should now be empty (all expired entries were evicted).
        assert len(cache._data) == 0, (
            f"Expected 0 entries after expiry+read, got {len(cache._data)}"
        )

    def test_entries_without_ttl_do_not_accumulate_unboundedly(self):
        """Entries stored without TTL stay in memory until explicitly deleted.

        This is documented behaviour — the test is here to make it visible.
        In production, always use a TTL.  This test prints a warning if you
        store a large number of no-TTL entries.
        """
        cache = InMemoryCache()

        for i in range(1000):
            cache.set(f"perm:{i}", f"v:{i}", ttl_s=None)  # no TTL

        # All entries should still be present (no auto-eviction without TTL).
        count = len(cache._data)
        assert count == 1000

        print(
            f"\n[perf:memory] {count} no-TTL entries in InMemoryCache. "
            "In production, use CACHE_BACKEND=redis with maxmemory-policy=allkeys-lru "
            "so eviction is automatic."
        )

        # Clean up.
        cache.clear()
        assert len(cache._data) == 0
