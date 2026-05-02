"""Concurrency tests for InMemoryCache and cache_aside.

Run with:
    cd backend && python -m pytest tests/concurrency/test_cache_concurrency.py -v

These tests probe two related concerns:

1. Thread safety of InMemoryCache itself.
   Python's GIL protects individual dict operations (get, set, pop) from
   data corruption, but multi-step read-modify-write sequences are not atomic.
   We verify there is no data corruption under concurrent access.

2. The thundering herd scenario.
   When many threads/requests arrive simultaneously at a cold cache, all of
   them miss and all call compute() concurrently.  This is expected behaviour
   (without a distributed lock), and these tests document it.

Why threads, not asyncio tasks?
--------------------------------
FastAPI is async, so "concurrent requests" in production are asyncio coroutines
that cooperate within a single OS thread.  The GIL does not protect them —
but a dict read/write from a coroutine is still a single operation at the
bytecode level.  For the purposes of InMemoryCache correctness, threading is
the more adversarial test (actual OS-level preemption), so it is the right
tool here.

Reading guide
-------------
Each test has a detailed docstring explaining WHAT is being verified and WHY
it matters.  Pay attention to the ``calls`` counters — they reveal how many
times the expensive compute function ran under concurrent load.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from modules.cache.decorators import cache_aside
from modules.cache.memory import InMemoryCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_concurrently(n: int, fn, barrier: threading.Barrier | None = None) -> list[Any]:
    """Run fn() in n threads simultaneously, return all results.

    If a barrier is provided, every thread waits on it before calling fn()
    so they all start at (approximately) the same moment.
    """
    results = [None] * n
    errors = []

    def worker(i):
        try:
            if barrier is not None:
                barrier.wait()
            results[i] = fn()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if errors:
        raise errors[0]  # surface the first error in the test

    return results


# ---------------------------------------------------------------------------
# 1. Thread safety of InMemoryCache
# ---------------------------------------------------------------------------

class TestInMemoryCacheThreadSafety:
    def test_concurrent_writes_to_different_keys_do_not_corrupt(self):
        """Writing to 100 different keys from 100 threads should leave all
        keys intact with their correct values.

        Python dict is thread-safe for individual operations under the GIL,
        so no corruption is expected — but this test would catch a regression
        if InMemoryCache ever switched to a lock-free structure that is not
        GIL-safe.
        """
        cache = InMemoryCache()
        n = 100

        def writer(i):
            cache.set(f"key:{i}", f"value:{i}", ttl_s=60)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every key must be present with the correct value.
        for i in range(n):
            assert cache.get(f"key:{i}") == f"value:{i}", f"key:{i} is missing or wrong"

    def test_concurrent_reads_do_not_raise(self):
        """100 threads reading the same key simultaneously should not raise."""
        cache = InMemoryCache()
        cache.set("shared", {"result": "ok"}, ttl_s=60)

        errors = []

        def reader():
            try:
                val = cache.get("shared")
                assert val == {"result": "ok"}
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent reads: {errors}"

    def test_concurrent_delete_does_not_raise(self):
        """Multiple threads deleting the same key simultaneously should not raise.

        InMemoryCache.delete() uses dict.pop(key, None) which is silent if the
        key is already absent — so concurrent deletes are safe.
        """
        cache = InMemoryCache()
        cache.set("k", "v")

        errors = []

        def deleter():
            try:
                cache.delete("k")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=deleter) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"delete() raised under concurrent access: {errors}"

    def test_write_then_read_is_consistent(self):
        """A value written in one thread is visible to a reader thread."""
        cache = InMemoryCache()
        written = threading.Event()

        def writer():
            cache.set("k", "written_value", ttl_s=60)
            written.set()

        def reader(result):
            written.wait()  # block until writer has set the value
            result.append(cache.get("k"))

        result = []
        t_write = threading.Thread(target=writer)
        t_read = threading.Thread(target=reader, args=(result,))

        t_write.start()
        t_read.start()
        t_write.join()
        t_read.join()

        assert result == ["written_value"]


# ---------------------------------------------------------------------------
# 2. Thundering herd behaviour (documented, not fixed yet)
# ---------------------------------------------------------------------------

class TestThunderingHerd:
    def test_cold_cache_all_threads_call_compute(self):
        """When the cache is cold and many threads arrive simultaneously, all of
        them miss and call compute() concurrently.

        This is the thundering herd problem.  Without a distributed mutex, this
        is the EXPECTED behaviour — it is not a bug.  This test documents the
        current behaviour so that:
          a) If you later add a mutex, you can change the assertion to
             ``assert call_count <= 2``  (at most a few compute() calls).
          b) If something accidentally serialises these calls, this test will
             tell you the thundering herd is gone and you can remove this note.

        WHY it is acceptable for traceflow right now:
          - Single-server dev tool; typical concurrency is 5-10 requests.
          - compute() hits Postgres on the same host; a few extra queries
            are not catastrophic.
          - Short TTL (30s) means the window during which this can happen is
            brief.
          - Adding a lock adds complexity that is not yet justified.
        """
        cache = InMemoryCache()
        call_count = 0
        barrier = threading.Barrier(10)

        def compute():
            nonlocal call_count
            call_count += 1
            time.sleep(0.02)  # simulate a real DB query (20ms)
            return "result"

        def task():
            barrier.wait()  # all threads start simultaneously
            return cache_aside(cache, "k", compute, ttl_s=60)

        results = _run_concurrently(10, task, barrier=barrier)

        # All threads should return the correct value.
        assert all(r == "result" for r in results), "Some threads got wrong values"

        # Print the call count for educational purposes.  Under the current
        # implementation (no mutex), this is likely to be > 1.
        print(f"\n[thundering herd] compute() was called {call_count} times by 10 concurrent threads")

        # The result is still correct even if compute() ran multiple times.
        assert call_count >= 1

    def test_warm_cache_no_thundering_herd(self):
        """When the cache is already warm (one request already populated it),
        concurrent requests all read from cache and compute() is NOT called.

        This is the normal "cache hit" case under load.
        """
        cache = InMemoryCache()
        call_count = 0

        # Warm up the cache with a single request before the concurrent storm.
        cache_aside(cache, "k", lambda: "warm", ttl_s=60)
        call_count = 0  # reset counter after warm-up

        def compute():
            nonlocal call_count
            call_count += 1
            return "warm"

        barrier = threading.Barrier(20)

        def task():
            barrier.wait()
            return cache_aside(cache, "k", compute, ttl_s=60)

        results = _run_concurrently(20, task, barrier=barrier)

        assert all(r == "warm" for r in results)
        # Once the cache is warm, compute() must never be called.
        assert call_count == 0, (
            f"compute() was called {call_count} times on a warm cache — "
            "this indicates a cache read bug"
        )

    def test_expiry_then_concurrent_requests_recompute_at_most_n_times(self):
        """When a cached entry expires and concurrent requests arrive, compute()
        may be called multiple times (thundering herd), but the final value
        in the cache is always correct.

        This test is a "document the expected maximum" style test.  We assert
        that compute() is called at most N times (where N = thread count), not
        exactly once — because without a mutex we cannot guarantee atomicity.
        """
        cache = InMemoryCache()
        call_count = 0
        n_threads = 5

        # Pre-populate with a very short TTL.
        cache.set("k", "old_value", ttl_s=1)
        time.sleep(1.1)  # let it expire

        barrier = threading.Barrier(n_threads)

        def compute():
            nonlocal call_count
            call_count += 1
            return "new_value"

        def task():
            barrier.wait()
            return cache_aside(cache, "k", compute, ttl_s=60)

        results = _run_concurrently(n_threads, task, barrier=barrier)

        assert all(r == "new_value" for r in results)
        # Without a mutex, up to n_threads compute() calls can happen.
        assert 1 <= call_count <= n_threads
        print(f"\n[post-expiry herd] compute() called {call_count}/{n_threads} times")
