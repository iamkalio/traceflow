"""TTL constants and jitter helper."""

from __future__ import annotations

import random


def jittered_ttl(base_ttl_s: int, jitter_pct: float = 0.1) -> int:
    """Return base_ttl_s ± up to (jitter_pct * base_ttl_s) seconds.

    The result is always at least 1 second so TTL is never zero or negative.

    Examples with default 10% jitter:
        jittered_ttl(30)  → integer in [27, 33]
        jittered_ttl(300) → integer in [270, 330]
    """
    delta = max(1, int(base_ttl_s * jitter_pct))
    return max(1, base_ttl_s + random.randint(-delta, delta))


# ------------------------------------------------------------------
# Canonical TTLs per data type.
#
# These are tuned for traceflow's access patterns:
#   - Trace lists change whenever a new trace is ingested; keep short.
#   - Individual trace detail is immutable after ingest; keep long.
#   - Insights are DB aggregations; expensive but 1-min staleness is fine.
#   - Eval results change when a background eval job finishes; keep short.
#
# Always wrap these with jittered_ttl() at the call site.
# ------------------------------------------------------------------

TRACE_LIST_TTL_S: int = 30
"""Trace list endpoint — new traces arrive frequently, so staleness must be
short.  Explicit invalidation on ingest is the primary freshness mechanism;
TTL is the safety net for edge cases."""

TRACE_DETAIL_TTL_S: int = 300
"""Individual trace detail — immutable after ingest, so a 5-minute TTL is
conservative and safe."""

INSIGHTS_TTL_S: int = 60
"""Insights rollup aggregation — heavy DB query; 1-minute lag is acceptable
for a summary dashboard."""

EVAL_RESULTS_TTL_S: int = 60
"""Eval results for a trace — updated when an async eval job completes.
Short TTL means stale results self-heal within a minute even without
explicit invalidation from the worker."""
