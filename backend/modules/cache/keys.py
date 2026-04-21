"""Cache key construction and versioning.

Design principles
-----------------
1. Namespace per domain: ``{version}:traceflow:{domain}:{discriminators}``
2. Version prefix: bump ``CacheVersion`` when the payload shape changes.
   Old keys become unreachable and expire naturally via TTL — no FLUSHALL
   needed during deploys.
3. All query parameters that affect the result are folded into the key.
   This is the most common mistake in rushed cache implementations: if you
   omit a filter from the key, two different queries share the same cache
   slot and one silently returns the other's results.
4. Long or variable-length filter combinations are hashed to keep key
   lengths short and predictable.  SHA-1 truncated to 12 hex chars (48 bits)
   is collision-resistant enough for this use case.

Invalidation cheat-sheet
--------------------------
  trace ingest     → delete trace_list_cursor_key(tenant_id, cursor=None)
                     (the unfiltered first page — most commonly cached key)
  eval completes   → delete eval_results_key(trace_id, eval_name)
                     and insights_summary_key(limit=100) (the default)
  schema changes   → bump CacheVersion; all old keys expire by TTL
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum


class CacheVersion(StrEnum):
    V1 = "v1"
    # When you change the shape of a cached payload (add/remove fields,
    # rename a key), bump this to V2 here.  All V1 keys will miss naturally
    # as they expire — no manual flush required.


def _hash_filters(**kwargs: object) -> str:
    """Produce a stable, short hex digest from all filter keyword arguments.

    Only non-None values contribute to the hash so that
    ``_hash_filters(q=None)`` and ``_hash_filters()`` produce the same string.

    Sort by key name for determinism across Python versions and call sites.

    Truncated to 12 hex characters (48 bits) which gives a collision
    probability of ~1 in 280 trillion for realistic key-space sizes.
    """
    canonical = "&".join(
        f"{k}={v}"
        for k, v in sorted(kwargs.items())
        if v is not None
    )
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


def trace_list_cursor_key(
    tenant_id: str | None,
    cursor: datetime | str | None,
    *,
    limit: int = 50,
    q: str | None = None,
    status: str | None = None,
    model: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    version: str = CacheVersion.V1,
) -> str:
    """Cache key for GET /v1/traces.

    ALL query parameters that affect the result are included in the hash.
    Changing any single parameter produces a completely different key, which
    means different filter combinations never share a cache slot.

    The tenant is extracted from the hash into the key path itself so that
    tenant-level invalidation ("invalidate all trace lists for tenant X") can
    be done with a Redis key-pattern scan in the future:
        SCAN 0 MATCH v1:traceflow:trace_list:tenant_x:*

    Key format:
        {version}:traceflow:trace_list:{tenant}:{filters_hash}
    """
    t = tenant_id or "_"
    c = cursor.isoformat() if isinstance(cursor, datetime) else (cursor or "_")

    filters_hash = _hash_filters(
        cursor=c,
        limit=limit,
        q=q,
        status=status,
        model=model,
        start_time=start_time.isoformat() if start_time else None,
        end_time=end_time.isoformat() if end_time else None,
    )
    return f"{version}:traceflow:trace_list:{t}:{filters_hash}"


def trace_detail_key(
    trace_id: str,
    *,
    version: str = CacheVersion.V1,
) -> str:
    """Cache key for GET /v1/traces/{trace_id}.

    Individual traces are immutable after ingest so this key is long-lived
    (see TRACE_DETAIL_TTL_S in ttl.py).

    Key format:
        {version}:traceflow:trace:{trace_id}
    """
    return f"{version}:traceflow:trace:{trace_id}"


def insights_summary_key(
    limit: int,
    *,
    version: str = CacheVersion.V1,
) -> str:
    """Cache key for GET /v1/insights/summary.

    The limit parameter changes which eval runs are included in the rollup,
    so it is part of the key.

    Key format:
        {version}:traceflow:insights:summary:{limit}
    """
    return f"{version}:traceflow:insights:summary:{limit}"


def eval_results_key(
    trace_id: str,
    eval_name: str | None,
    *,
    version: str = CacheVersion.V1,
) -> str:
    """Cache key for GET /v1/traces/{trace_id}/evals.

    Scoped by both trace_id and eval_name so that different evaluators
    (e.g. groundedness_v1 vs toxicity_v1) have independent cache slots
    and can be invalidated selectively.

    ``eval_name=None`` means "all evaluators for this trace".

    Key format:
        {version}:traceflow:eval_results:{trace_id}:{eval_name}
    """
    e = eval_name or "_"
    return f"{version}:traceflow:eval_results:{trace_id}:{e}"
