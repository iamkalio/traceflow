"""Unit tests for the TTL jitter helper.

Run with:
    cd backend && python -m pytest tests/unit/cache/test_ttl.py -v

The jittered_ttl() function is simple, so the tests are short.
We verify:
  1. Output is within the expected jitter window.
  2. Output is always a positive integer.
  3. Distribution is not always identical to the base TTL (i.e. jitter fires).
  4. Edge cases (base_ttl=0, base_ttl=1) do not produce zero or negative TTLs.
"""

from __future__ import annotations

import pytest

from modules.cache.ttl import (
    EVAL_RESULTS_TTL_S,
    INSIGHTS_TTL_S,
    TRACE_DETAIL_TTL_S,
    TRACE_LIST_TTL_S,
    jittered_ttl,
)


# ------------------------------------------------------------------
# jittered_ttl
# ------------------------------------------------------------------

class TestJitteredTtl:
    def test_result_within_10pct_window_by_default(self):
        """Default 10% jitter: result is in [base*0.9, base*1.1]."""
        base = 30
        delta = max(1, int(base * 0.1))
        for _ in range(50):
            result = jittered_ttl(base)
            assert base - delta <= result <= base + delta, (
                f"jittered_ttl({base}) = {result} is outside [{base - delta}, {base + delta}]"
            )

    def test_result_within_custom_jitter_window(self):
        """A custom jitter_pct of 0.2 gives a 20% window."""
        base = 100
        jitter = 0.2
        delta = max(1, int(base * jitter))
        for _ in range(50):
            result = jittered_ttl(base, jitter_pct=jitter)
            assert base - delta <= result <= base + delta

    def test_result_is_always_at_least_one(self):
        """TTL must never be zero or negative — that would mean 'no expiry' or invalid."""
        for _ in range(100):
            assert jittered_ttl(1) >= 1
            assert jittered_ttl(0) >= 1  # edge case: base=0

    def test_result_is_integer(self):
        """TTL must be an integer because redis-py's setex requires int seconds."""
        for base in [1, 10, 30, 60, 300]:
            result = jittered_ttl(base)
            assert isinstance(result, int), f"jittered_ttl({base}) returned {type(result)}"

    def test_jitter_is_actually_applied(self):
        """Over many calls, the result is not always exactly equal to base_ttl.

        If every call returned the base TTL, jitter would be a no-op and the
        thundering herd problem would not be mitigated.
        """
        base = 30
        results = {jittered_ttl(base) for _ in range(100)}
        # With a uniform distribution over [27, 33], we expect more than one
        # distinct value in 100 draws.  This assertion would only fail if the
        # random number generator is broken or the jitter is zero.
        assert len(results) > 1, "jitter did not produce any variation over 100 calls"

    def test_large_base_ttl(self):
        """Large TTLs (e.g. one hour) produce valid results."""
        base = 3600
        delta = max(1, int(base * 0.1))
        result = jittered_ttl(base)
        assert isinstance(result, int)
        assert base - delta <= result <= base + delta


# ------------------------------------------------------------------
# Canonical TTL constants
# ------------------------------------------------------------------

class TestTtlConstants:
    """Smoke-check that the canonical constants are reasonable positive integers."""

    def test_trace_list_ttl_is_positive_int(self):
        assert isinstance(TRACE_LIST_TTL_S, int)
        assert TRACE_LIST_TTL_S > 0

    def test_trace_detail_ttl_is_positive_int(self):
        assert isinstance(TRACE_DETAIL_TTL_S, int)
        assert TRACE_DETAIL_TTL_S > 0

    def test_insights_ttl_is_positive_int(self):
        assert isinstance(INSIGHTS_TTL_S, int)
        assert INSIGHTS_TTL_S > 0

    def test_eval_results_ttl_is_positive_int(self):
        assert isinstance(EVAL_RESULTS_TTL_S, int)
        assert EVAL_RESULTS_TTL_S > 0

    def test_ttl_ordering_matches_expected_volatility(self):
        """Trace lists change more often than individual trace details.
        Insights are in between.  Verify the TTL ordering reflects this.

        If this assertion fails, someone changed a constant to a value that
        does not match the data's actual update frequency — review it.
        """
        # Lists expire soonest; detail entries expire latest.
        assert TRACE_LIST_TTL_S <= INSIGHTS_TTL_S
        assert INSIGHTS_TTL_S <= TRACE_DETAIL_TTL_S
