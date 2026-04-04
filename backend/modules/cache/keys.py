"""
Cache key design & invalidation notes.

**Principles**
- Namespace keys per domain: ``traceflow:{domain}:v{n}:…``.
- Bump ``v{n}`` when payload shape changes (invalidates without Redis FLUSH).
- Prefer coarse keys + short TTL for list endpoints; narrow keys for entity detail.

**Invalidation (when you add Redis)**
- On trace ingest for ``trace_id``: invalidate ``trace_detail:*:trace_id``, ``trace_list:*`` (or rely on TTL).
- On eval completion: invalidate insight rollups or use short TTL (e.g. 30s).

See ``decorators.cache_aside`` for a safe get-or-compute helper.
"""

from __future__ import annotations

from enum import StrEnum


class CacheVersion(StrEnum):
    V1 = "v1"


def trace_list_cursor_key(
    tenant_id: str | None,
    cursor: str | None,
    *,
    version: str = CacheVersion.V1,
) -> str:
    t = tenant_id or "_"
    c = cursor or "_"
    return f"{version}:traceflow:trace_list:{t}:{c}"


def trace_detail_key(
    trace_id: str,
    *,
    version: str = CacheVersion.V1,
) -> str:
    return f"{version}:traceflow:trace:{trace_id}"


def insights_summary_key(
    limit: int,
    *,
    version: str = CacheVersion.V1,
) -> str:
    return f"{version}:traceflow:insights:summary:{limit}"
