"""In-process cache backed by a plain dict.

Use this backend in:
  - local development (single-process uvicorn)
  - tests (fast, no infra needed)

Do NOT use in multi-worker production deployments. Each worker process
gets its own independent dict, so caches diverge and invalidations made
by one worker are invisible to others. Use RedisCache instead.
"""

from __future__ import annotations

import time
from typing import Any


class InMemoryCache:
    """Dict-backed cache with lazy TTL expiry.

    Entries are stored as ``(value, expires_at)`` tuples where
    ``expires_at`` is a ``time.monotonic()`` float or ``None`` (no expiry).
    Expiry is checked on every ``get()``; there is no background sweeper.
    This is called "lazy eviction" — stale entries live in memory until
    they are next read, then they're removed.  For small caches this is
    fine; for large caches a background sweep is worth adding later.
    """

    def __init__(self) -> None:
        # key → (value, expires_at_monotonic | None)
        # None expiry means the entry lives until explicitly deleted.
        self._data: dict[str, tuple[Any, float | None]] = {}

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None if the key is absent or expired.

        A return value of None always means "cache miss" — this is the
        contract that cache_aside() relies on.  Do not store literal None
        as a value; use the _CACHED_NONE sentinel in decorators.py instead.
        """
        entry = self._data.get(key)
        if entry is None:
            return None

        value, expires_at = entry

        # Check expiry. We use pop() instead of del to be safe under
        # concurrent access — a second thread may have already removed
        # the key between our get() and this del.
        if expires_at is not None and time.monotonic() > expires_at:
            self._data.pop(key, None)  # lazy eviction
            return None

        return value

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        """Store value under key.

        If ttl_s is given, the entry expires that many seconds from now
        (measured in monotonic time, so clock adjustments don't affect it).
        If ttl_s is None, the entry never expires — avoid this in production
        or your process will eventually run out of memory.
        """
        expires_at = time.monotonic() + ttl_s if ttl_s is not None else None
        self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        """Remove key if present; silently a no-op if absent."""
        self._data.pop(key, None)

    def clear(self) -> None:
        """Remove all entries.

        Called in test teardown (via conftest.py) to guarantee isolation
        between test cases.  Not normally needed in production code.
        """
        self._data.clear()
