"""Redis-backed cache for production use.

This backend is safe for multi-worker deployments because all workers share
the same Redis instance, so a cache write or invalidation from one worker is
immediately visible to all others.

Wiring
------
Set ``CACHE_BACKEND=redis`` in your environment (or docker-compose).
``modules.cache.get_cache()`` will then return a ``RedisCache`` instance
built from ``REDIS_CACHE_URL`` (falls back to ``REDIS_URL`` from core.config).

Serialisation
-------------
Values are serialised to JSON on write and deserialised on read.
  - ``json.dumps(value, default=str)`` converts types like ``datetime`` to
    strings rather than raising TypeError.
  - On read, ``json.loads()`` returns plain Python dicts/lists/strings.
    Callers are responsible for re-validating into Pydantic models if needed
    (use ``.model_validate(cached_dict)`` at the call site).
  - If a value cannot be JSON-serialised, ``set()`` raises ValueError rather
    than silently failing.

TTL
---
Always pass ``ttl_s`` — entries without TTL are not automatically evicted
and will grow Redis memory without bound.  ``set()`` warns when called with
``ttl_s=None`` so this mistake is visible in logs.

Failure handling
----------------
Network or Redis errors propagate as ``redis.RedisError`` exceptions.
The caller (``cache_aside`` in decorators.py) catches these and degrades
gracefully so that a Redis outage never takes down the application.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis as redis_lib

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-backed cache using the redis-py sync client.

    ``decode_responses=True`` is set so that ``get()`` returns ``str | None``
    rather than ``bytes | None``, which makes JSON parsing straightforward.
    """

    def __init__(self, url: str) -> None:
        # decode_responses=True: Redis returns str, not bytes.
        # socket_timeout / socket_connect_timeout: fail fast so that a slow
        # Redis doesn't hold up every HTTP request.
        self._client: redis_lib.Redis = redis_lib.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )

    # ------------------------------------------------------------------
    # CacheBackend interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """Return the deserialised value, or None on miss or parse error.

        A parse error (malformed JSON) is treated as a miss and logged as a
        warning rather than surfaced as an exception, because a corrupted
        cache entry should never crash a request.
        """
        raw: str | None = self._client.get(key)  # type: ignore[assignment]
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Corrupted or unexpected value in Redis. Treat as miss so the
            # caller falls back to the source of truth.
            logger.warning("cache: malformed JSON for key=%r, treating as miss", key)
            return None

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        """Serialise value to JSON and write to Redis.

        If ``ttl_s`` is None, the entry is stored without expiry.  This is
        intentionally warned on because unbounded entries are almost always a
        mistake in a caching context.
        """
        if ttl_s is None:
            logger.warning(
                "cache: set() called with no TTL for key=%r — "
                "entry will never expire; set an explicit ttl_s",
                key,
            )

        try:
            serialised = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"cache: value for key={key!r} is not JSON-serialisable"
            ) from exc

        if ttl_s is not None:
            # SETEX stores the key with an integer-second TTL atomically.
            self._client.setex(name=key, time=ttl_s, value=serialised)
        else:
            self._client.set(key, serialised)

    def delete(self, key: str) -> None:
        """Delete key; no-op if the key does not exist."""
        self._client.delete(key)

    # ------------------------------------------------------------------
    # Extras (not part of the CacheBackend Protocol but useful for ops)
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if Redis is reachable.

        Use this in a ``/healthz`` endpoint or startup check to surface
        Redis connectivity problems early rather than at request time.
        """
        try:
            return bool(self._client.ping())
        except redis_lib.RedisError:
            return False

    def clear(self) -> None:
        """Flush the entire Redis database.

        Only intended for use in tests with a dedicated test-only Redis DB
        (e.g., DB index 1, set via REDIS_CACHE_URL).  Never call this against
        a shared or production Redis.
        """
        self._client.flushdb()
