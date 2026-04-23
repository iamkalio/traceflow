"""Unit tests for InMemoryCache.

Run with:
    cd backend && python -m pytest tests/unit/cache/test_memory.py -v

Each test here exercises one specific behaviour of InMemoryCache in isolation.
No FastAPI, no DB, no Redis — just the cache class itself.

How to read these tests
-----------------------
Every test has a short docstring explaining WHAT behaviour it is asserting
and WHY that behaviour matters.  Read the docstring before the code.
"""

from __future__ import annotations

import time

import pytest

from modules.cache.memory import InMemoryCache


# ------------------------------------------------------------------
# Basic get / set / delete
# ------------------------------------------------------------------

def test_set_and_get_returns_stored_value():
    """A value stored with set() is returned by get()."""
    cache = InMemoryCache()
    cache.set("k", "hello")
    assert cache.get("k") == "hello"


def test_get_returns_none_for_missing_key():
    """get() on an absent key returns None (the cache-miss sentinel)."""
    cache = InMemoryCache()
    assert cache.get("nonexistent") is None


def test_set_overwrites_existing_value():
    """A second set() on the same key replaces the first value."""
    cache = InMemoryCache()
    cache.set("k", "first")
    cache.set("k", "second")
    assert cache.get("k") == "second"


def test_delete_removes_key():
    """delete() makes the key absent so get() returns None."""
    cache = InMemoryCache()
    cache.set("k", "value")
    cache.delete("k")
    assert cache.get("k") is None


def test_delete_on_absent_key_is_silent():
    """delete() on a key that was never set does not raise."""
    cache = InMemoryCache()
    cache.delete("never_set")  # should not raise


def test_different_keys_are_independent():
    """Two different keys each return their own independent value."""
    cache = InMemoryCache()
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1
    assert cache.get("b") == 2


# ------------------------------------------------------------------
# TTL expiry
# ------------------------------------------------------------------

def test_entry_without_ttl_never_expires():
    """An entry stored with ttl_s=None is still present after 100ms.

    This is the expected behaviour for entries that are explicitly invalidated
    by write-path code rather than relying on time-based expiry.
    """
    cache = InMemoryCache()
    cache.set("k", "permanent", ttl_s=None)
    time.sleep(0.1)
    assert cache.get("k") == "permanent"


def test_entry_with_ttl_expires_after_ttl():
    """An entry stored with ttl_s=1 is gone after 1.1 seconds.

    This test would have FAILED against the original InMemoryCache because it
    discarded the ttl_s argument entirely (_ = ttl_s).  It is the regression
    test that proves the TTL fix is correct.
    """
    cache = InMemoryCache()
    cache.set("k", "temporary", ttl_s=1)

    # Before expiry: key is present.
    assert cache.get("k") == "temporary"

    time.sleep(1.1)  # wait for TTL to pass

    # After expiry: get() returns None — the entry was lazily evicted.
    assert cache.get("k") is None


def test_entry_is_present_just_before_ttl():
    """An entry is still present while its TTL has not yet elapsed."""
    cache = InMemoryCache()
    cache.set("k", "alive", ttl_s=2)
    time.sleep(0.5)
    # 0.5s < 2s: key must still be readable
    assert cache.get("k") == "alive"


def test_expired_entry_is_evicted_on_read():
    """Reading an expired entry removes it from internal storage (lazy eviction).

    This verifies that memory is not unbounded: once an entry is read past its
    TTL, the underlying dict entry is cleaned up.
    """
    cache = InMemoryCache()
    cache.set("k", "will_expire", ttl_s=1)
    time.sleep(1.1)

    # The read triggers lazy eviction.
    assert cache.get("k") is None
    # Confirm the key is no longer in internal storage.
    assert "k" not in cache._data


def test_set_with_new_ttl_resets_expiry():
    """Calling set() again on an expired key refreshes the entry with a new TTL."""
    cache = InMemoryCache()
    cache.set("k", "v1", ttl_s=1)
    time.sleep(1.1)

    # Re-set the key after expiry.
    cache.set("k", "v2", ttl_s=10)
    assert cache.get("k") == "v2"


# ------------------------------------------------------------------
# Various value types
# ------------------------------------------------------------------

def test_stores_dict():
    """Dicts (the most common cached type for API responses) round-trip correctly."""
    cache = InMemoryCache()
    payload = {"items": [{"trace_id": "abc", "name": "my-trace"}], "next_cursor": None}
    cache.set("k", payload)
    assert cache.get("k") == payload


def test_stores_list():
    """Lists (e.g. a list of span dicts) round-trip correctly."""
    cache = InMemoryCache()
    spans = [{"span_id": "s1"}, {"span_id": "s2"}]
    cache.set("k", spans)
    assert cache.get("k") == spans


def test_stores_empty_list():
    """An empty list is a legitimate value, not a falsy miss.

    Without the _CACHED_NONE sentinel pattern in cache_aside, storing []
    and then calling cache_aside again would produce a miss (because
    ``if raw is not None`` would be True for []).  InMemoryCache itself does
    not know about the sentinel — it just stores and retrieves whatever it
    is given.  This test confirms that [] is stored and returned as-is.
    """
    cache = InMemoryCache()
    cache.set("k", [])
    assert cache.get("k") == []


def test_stores_integer_zero():
    """0 is a legitimate cached value and must not be confused with a miss."""
    cache = InMemoryCache()
    cache.set("k", 0)
    assert cache.get("k") == 0


# ------------------------------------------------------------------
# clear()
# ------------------------------------------------------------------

def test_clear_removes_all_entries():
    """clear() empties the entire cache."""
    cache = InMemoryCache()
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") is None
    assert cache._data == {}


def test_clear_on_empty_cache_is_safe():
    """clear() on an already-empty cache does not raise."""
    cache = InMemoryCache()
    cache.clear()  # should not raise
