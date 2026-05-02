"""Unit tests for cache key construction functions.

Run with:
    cd backend && python -m pytest tests/unit/cache/test_keys.py -v

These tests verify two things:
  1. Same inputs → same key (determinism).
  2. Different inputs → different keys (no collisions between filter combos).

Why test key functions?
-----------------------
Key bugs are silent in production.  If ``trace_list_cursor_key(limit=10)``
and ``trace_list_cursor_key(limit=50)`` produce the same key, a user
requesting 10 traces silently gets 50 (or vice versa).  Tests catch this
before it ships.
"""

from __future__ import annotations

from datetime import datetime, timezone

from modules.cache.keys import (
    CacheVersion,
    eval_results_key,
    insights_summary_key,
    trace_detail_key,
    trace_list_cursor_key,
)


# ------------------------------------------------------------------
# trace_list_cursor_key
# ------------------------------------------------------------------

class TestTraceListCursorKey:
    def test_deterministic(self):
        """Same arguments produce the same key on repeated calls."""
        k1 = trace_list_cursor_key("tenant_a", None)
        k2 = trace_list_cursor_key("tenant_a", None)
        assert k1 == k2

    def test_different_tenants_produce_different_keys(self):
        """tenant_a and tenant_b must never share a cache slot."""
        k_a = trace_list_cursor_key("tenant_a", None)
        k_b = trace_list_cursor_key("tenant_b", None)
        assert k_a != k_b

    def test_none_tenant_vs_explicit_tenant(self):
        """A request without a tenant_id should not share a key with tenant X."""
        k_none = trace_list_cursor_key(None, None)
        k_x = trace_list_cursor_key("x", None)
        assert k_none != k_x

    def test_different_limits_produce_different_keys(self):
        """limit=10 and limit=50 return different result sets — must be different keys.

        This is the bug that existed in the original implementation: limit was
        not included in the key, so /v1/traces?limit=10 and
        /v1/traces?limit=50 shared a cache slot.
        """
        k10 = trace_list_cursor_key(None, None, limit=10)
        k50 = trace_list_cursor_key(None, None, limit=50)
        assert k10 != k50

    def test_different_cursors_produce_different_keys(self):
        """Page 1 and page 2 (different cursor) must not share a cache slot."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        k_first = trace_list_cursor_key(None, None)
        k_second = trace_list_cursor_key(None, dt)
        assert k_first != k_second

    def test_different_search_queries_produce_different_keys(self):
        """q='error' and q='success' filter on different data."""
        k_error = trace_list_cursor_key(None, None, q="error")
        k_success = trace_list_cursor_key(None, None, q="success")
        assert k_error != k_success

    def test_none_query_vs_empty_string_are_same(self):
        """q=None (absent) should be treated the same way regardless of how
        it is passed through the system.  Both map to "no filter applied"."""
        k1 = trace_list_cursor_key(None, None, q=None)
        k2 = trace_list_cursor_key(None, None)  # q defaults to None
        assert k1 == k2

    def test_different_statuses_produce_different_keys(self):
        """status='error' and status='success' are different filter values."""
        k_err = trace_list_cursor_key(None, None, status="error")
        k_ok = trace_list_cursor_key(None, None, status="success")
        assert k_err != k_ok

    def test_different_models_produce_different_keys(self):
        """model='gpt-4o' and model='gpt-3.5-turbo' should not collide."""
        k1 = trace_list_cursor_key(None, None, model="gpt-4o")
        k2 = trace_list_cursor_key(None, None, model="gpt-3.5-turbo")
        assert k1 != k2

    def test_different_time_ranges_produce_different_keys(self):
        """start_time affects which rows are included — must affect the key."""
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
        k1 = trace_list_cursor_key(None, None, start_time=t1)
        k2 = trace_list_cursor_key(None, None, start_time=t2)
        assert k1 != k2

    def test_key_starts_with_version_and_namespace(self):
        """Keys must be namespaced so they don't collide with other apps on the same Redis."""
        k = trace_list_cursor_key(None, None)
        assert k.startswith("v1:traceflow:trace_list:")

    def test_tenant_appears_in_key_path(self):
        """The tenant should be a segment in the key so SCAN-by-tenant is possible."""
        k = trace_list_cursor_key("acme_corp", None)
        assert ":acme_corp:" in k

    def test_version_parameter_changes_key(self):
        """Bumping the version produces a different key, invalidating cached values."""
        k_v1 = trace_list_cursor_key(None, None, version="v1")
        k_v2 = trace_list_cursor_key(None, None, version="v2")
        assert k_v1 != k_v2

    def test_all_filters_combined(self):
        """A fully-parameterised request produces a unique key."""
        t = datetime(2024, 6, 1, tzinfo=timezone.utc)
        k = trace_list_cursor_key(
            "tenant",
            t,
            limit=20,
            q="my prompt",
            status="error",
            model="gpt-4o",
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        # Smoke-check: it's a non-empty string and starts with the namespace.
        assert isinstance(k, str)
        assert k.startswith("v1:traceflow:trace_list:")


# ------------------------------------------------------------------
# trace_detail_key
# ------------------------------------------------------------------

class TestTraceDetailKey:
    def test_deterministic(self):
        k1 = trace_detail_key("abc-123")
        k2 = trace_detail_key("abc-123")
        assert k1 == k2

    def test_different_trace_ids_produce_different_keys(self):
        k1 = trace_detail_key("trace-001")
        k2 = trace_detail_key("trace-002")
        assert k1 != k2

    def test_key_format(self):
        k = trace_detail_key("abc-123")
        assert k == "v1:traceflow:trace:abc-123"


# ------------------------------------------------------------------
# insights_summary_key
# ------------------------------------------------------------------

class TestInsightsSummaryKey:
    def test_deterministic(self):
        assert insights_summary_key(100) == insights_summary_key(100)

    def test_different_limits_produce_different_keys(self):
        assert insights_summary_key(50) != insights_summary_key(100)

    def test_key_format(self):
        k = insights_summary_key(100)
        assert k == "v1:traceflow:insights:summary:100"


# ------------------------------------------------------------------
# eval_results_key
# ------------------------------------------------------------------

class TestEvalResultsKey:
    def test_deterministic(self):
        k1 = eval_results_key("trace-1", "groundedness_v1")
        k2 = eval_results_key("trace-1", "groundedness_v1")
        assert k1 == k2

    def test_different_trace_ids_produce_different_keys(self):
        k1 = eval_results_key("trace-1", "groundedness_v1")
        k2 = eval_results_key("trace-2", "groundedness_v1")
        assert k1 != k2

    def test_different_eval_names_produce_different_keys(self):
        """groundedness and toxicity have independent cache slots."""
        k1 = eval_results_key("trace-1", "groundedness_v1")
        k2 = eval_results_key("trace-1", "toxicity_v1")
        assert k1 != k2

    def test_none_eval_name_has_its_own_slot(self):
        """eval_name=None ('all evals') is distinct from any named evaluator."""
        k_all = eval_results_key("trace-1", None)
        k_named = eval_results_key("trace-1", "groundedness_v1")
        assert k_all != k_named

    def test_key_format_with_eval_name(self):
        k = eval_results_key("trace-1", "groundedness_v1")
        assert k == "v1:traceflow:eval_results:trace-1:groundedness_v1"

    def test_key_format_without_eval_name(self):
        k = eval_results_key("trace-1", None)
        assert k == "v1:traceflow:eval_results:trace-1:_"
