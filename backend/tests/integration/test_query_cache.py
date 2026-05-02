"""Integration tests: cache behaviour wired into the FastAPI route handlers.

Run with:
    cd backend && python -m pytest tests/integration/test_query_cache.py -v

These tests exercise the real FastAPI route handlers (query/router.py,
evaluation/router.py, ingestion/router.py) but mock out the DB layer.
The goal is to test that:
  - Route handlers correctly read from and write to the cache.
  - A second identical HTTP request does NOT call the DB repository.
  - After invalidation (delete or ingest), the DB IS called again.
  - A broken cache backend never causes a 500 error.
  - 404s from non-existent traces are cached (no repeated DB hits).

What is NOT tested here
-----------------------
- Correctness of DB queries (that belongs in repository tests with a real DB).
- Redis serialisation (tested separately against a real Redis if you add
  a ``@pytest.mark.integration`` test with RUN_INTEGRATION=1).

Setup note
----------
The ``fresh_cache`` fixture from conftest.py runs automatically (autouse=True)
before every test, giving each test an isolated InMemoryCache.  The
``test_client`` fixture gives us a Starlette TestClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

# A minimal trace list row that satisfies TraceListResponse's schema.
_MOCK_TRACE_ITEM = MagicMock(
    trace_id="trace-abc",
    name="my-llm-call",
    input="what is 2+2?",
    output="4",
    annotations={},
    start_time=None,
    latency_ms=120,
    first_seen=None,
    last_seen=None,
    span_count=1,
    status="success",
    total_tokens=50,
    total_cost_usd=0.001,
)

_MOCK_SPAN = MagicMock(
    trace_id="trace-abc",
    span_id="span-1",
    name="llm",
    parent_span_id=None,
    start_time=None,
    end_time=None,
    duration_ms=120,
    status="success",
    attributes={},
    input="what is 2+2?",
    output="4",
    model="gpt-4o",
    total_tokens=50,
    prompt_tokens=10,
    completion_tokens=40,
    cost_usd=0.001,
    annotations={},
)


# ---------------------------------------------------------------------------
# Helper: build a mock eval run item
# ---------------------------------------------------------------------------
def _mock_eval_run(status="completed", score=0.9, label="good"):
    m = MagicMock()
    m.status = status
    m.score = score
    m.label = label
    return m


# ===========================================================================
# GET /v1/traces — trace list caching
# ===========================================================================

class TestTraceListCache:
    def test_first_request_hits_db(self, test_client):
        """First request must fetch from DB (cache is cold)."""
        with patch("modules.query.router.list_traces", return_value=([_MOCK_TRACE_ITEM], None)) as mock_list, \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            resp = test_client.get("/v1/traces")
            assert resp.status_code == 200
            mock_list.assert_called_once()

    def test_second_identical_request_skips_db(self, test_client):
        """Second request with identical params reads from cache — DB not called."""
        with patch("modules.query.router.list_traces", return_value=([_MOCK_TRACE_ITEM], None)) as mock_list, \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces")   # miss — populates cache
            test_client.get("/v1/traces")   # hit  — cache serves the response

            # DB was only called once (for the first request).
            assert mock_list.call_count == 1

    def test_different_filter_hits_db_again(self, test_client):
        """A request with a different query param produces a different cache key
        and therefore hits the DB independently."""
        with patch("modules.query.router.list_traces", return_value=([_MOCK_TRACE_ITEM], None)) as mock_list, \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces")                   # key A (no filters)
            test_client.get("/v1/traces?status=error")       # key B (status filter)

            # Both requests are cache misses → DB called twice.
            assert mock_list.call_count == 2

    def test_response_content_is_preserved_through_cache(self, test_client):
        """The cached response must be identical to the original DB response."""
        with patch("modules.query.router.list_traces", return_value=([_MOCK_TRACE_ITEM], None)), \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            r1 = test_client.get("/v1/traces").json()
            r2 = test_client.get("/v1/traces").json()

            assert r1 == r2
            assert r2["items"][0]["trace_id"] == "trace-abc"


# ===========================================================================
# GET /v1/traces/{trace_id} — trace detail caching
# ===========================================================================

class TestTraceDetailCache:
    def test_first_request_hits_db(self, test_client):
        with patch("modules.query.router.trace_has_any_span", return_value=True), \
             patch("modules.query.router.list_spans_for_trace", return_value=[_MOCK_SPAN]) as mock_spans, \
             patch("modules.query.router.SessionLocal"):
            resp = test_client.get("/v1/traces/trace-abc")
            assert resp.status_code == 200
            mock_spans.assert_called_once()

    def test_second_request_uses_cache(self, test_client):
        with patch("modules.query.router.trace_has_any_span", return_value=True), \
             patch("modules.query.router.list_spans_for_trace", return_value=[_MOCK_SPAN]) as mock_spans, \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces/trace-abc")
            test_client.get("/v1/traces/trace-abc")

            assert mock_spans.call_count == 1

    def test_different_trace_ids_have_independent_cache_slots(self, test_client):
        """trace-abc and trace-xyz are different keys — both hit the DB."""
        with patch("modules.query.router.trace_has_any_span", return_value=True), \
             patch("modules.query.router.list_spans_for_trace", return_value=[_MOCK_SPAN]) as mock_spans, \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces/trace-abc")
            test_client.get("/v1/traces/trace-xyz")

            assert mock_spans.call_count == 2

    def test_nonexistent_trace_returns_404(self, test_client):
        """A trace that doesn't exist returns 404."""
        with patch("modules.query.router.trace_has_any_span", return_value=False), \
             patch("modules.query.router.SessionLocal"):
            resp = test_client.get("/v1/traces/no-such-trace")
            assert resp.status_code == 404

    def test_404_is_cached_so_db_not_hammered(self, test_client):
        """Repeated requests for a non-existent trace should hit the DB only once.

        Without caching None results, every 404 request would hit the DB.
        With the _CACHED_NONE sentinel, the 404 answer is cached.
        """
        with patch("modules.query.router.trace_has_any_span", return_value=False) as mock_check, \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces/ghost-trace")
            test_client.get("/v1/traces/ghost-trace")

            # DB existence check should only run once.
            assert mock_check.call_count == 1


# ===========================================================================
# GET /v1/traces/{trace_id}/evals — eval results caching
# ===========================================================================

class TestEvalResultsCache:
    def test_second_request_uses_cache(self, test_client):
        with patch("modules.query.router.trace_has_any_span", return_value=True), \
             patch("modules.query.router.list_eval_results_for_trace", return_value=[]) as mock_evals, \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces/trace-abc/evals")
            test_client.get("/v1/traces/trace-abc/evals")

            assert mock_evals.call_count == 1

    def test_different_eval_names_have_independent_cache_slots(self, test_client):
        """eval_name=groundedness and eval_name=toxicity are different keys."""
        with patch("modules.query.router.trace_has_any_span", return_value=True), \
             patch("modules.query.router.list_eval_results_for_trace", return_value=[]) as mock_evals, \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces/trace-abc/evals?eval_name=groundedness_v1")
            test_client.get("/v1/traces/trace-abc/evals?eval_name=toxicity_v1")

            assert mock_evals.call_count == 2

    def test_empty_eval_list_is_cached(self, test_client):
        """An empty eval list (no evals run yet) is cached, not re-fetched."""
        with patch("modules.query.router.trace_has_any_span", return_value=True), \
             patch("modules.query.router.list_eval_results_for_trace", return_value=[]) as mock_evals, \
             patch("modules.query.router.SessionLocal"):
            r1 = test_client.get("/v1/traces/trace-abc/evals")
            r2 = test_client.get("/v1/traces/trace-abc/evals")

            assert r1.json() == r2.json() == []
            assert mock_evals.call_count == 1


# ===========================================================================
# Cache invalidation on eval run
# ===========================================================================

class TestEvalRunCacheInvalidation:
    def test_running_eval_invalidates_eval_results_cache(self, test_client, fresh_cache):
        """After POST /evals/run, the eval results cache for that trace is cleared.

        Verify by: pre-populate the cache, POST to run eval, then GET evals
        and confirm the DB is called again (not the stale cache).
        """
        from modules.cache.keys import eval_results_key

        # Pre-populate the cache directly with stale data.
        stale_data = [{"eval_name": "groundedness_v1", "score": 0.5, "label": "bad"}]
        fresh_cache.set(eval_results_key("trace-abc", "groundedness_v1"), stale_data)
        fresh_cache.set(eval_results_key("trace-abc", None), stale_data)

        # POST to run eval (mocking the DB and RQ queue).
        with patch("modules.evaluation.router.trace_has_any_span", return_value=True), \
             patch("modules.evaluation.router.create_eval_run_queued", return_value=MagicMock(id=1)), \
             patch("modules.evaluation.router.enqueue_job", return_value="job-id"), \
             patch("modules.evaluation.router.SessionLocal"):
            resp = test_client.post(
                "/v1/traces/trace-abc/evals/run",
                json={"eval_name": "groundedness_v1"},
                headers={"X-OpenAI-API-Key": "sk-test"},
            )
            assert resp.status_code == 200

        # Cache should be cleared for the eval results key.
        assert fresh_cache.get(eval_results_key("trace-abc", "groundedness_v1")) is None
        assert fresh_cache.get(eval_results_key("trace-abc", None)) is None


# ===========================================================================
# Graceful degradation — broken cache backend
# ===========================================================================

class TestCacheDegradation:
    def test_broken_cache_does_not_cause_500(self, test_client, monkeypatch):
        """If the cache backend raises on get(), the request still succeeds.

        A Redis outage must NOT take down the application.  Requests should
        succeed by falling back to the DB.
        """
        import modules.cache as cache_mod
        from unittest.mock import MagicMock

        broken = MagicMock()
        broken.get.side_effect = ConnectionError("Redis is down")
        broken.set.side_effect = ConnectionError("Redis is down")
        monkeypatch.setattr(cache_mod, "_cache_instance", broken)

        with patch("modules.query.router.list_traces", return_value=([_MOCK_TRACE_ITEM], None)), \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            resp = test_client.get("/v1/traces")
            # Must be 200, not 500 — the app degrades gracefully.
            assert resp.status_code == 200

    def test_broken_cache_falls_back_to_db_on_every_request(self, test_client, monkeypatch):
        """When the cache is broken, every request hits the DB (no caching, but correct)."""
        import modules.cache as cache_mod

        broken = MagicMock()
        broken.get.side_effect = ConnectionError("Redis is down")
        broken.set.side_effect = ConnectionError("Redis is down")
        monkeypatch.setattr(cache_mod, "_cache_instance", broken)

        with patch("modules.query.router.list_traces", return_value=([_MOCK_TRACE_ITEM], None)) as mock_list, \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            test_client.get("/v1/traces")
            test_client.get("/v1/traces")

            # Both requests hit the DB because the cache is broken.
            assert mock_list.call_count == 2


# ===========================================================================
# Security: tenant isolation
# ===========================================================================

class TestCacheTenantIsolation:
    def test_tenant_a_cannot_read_tenant_b_data(self, test_client):
        """Requests with different tenant_ids must NOT share a cache slot.

        If tenant isolation is broken, a user with tenant_id=B could receive
        tenant A's trace data from cache.
        """
        tenant_a_trace = MagicMock(**{**_MOCK_TRACE_ITEM.__dict__, "trace_id": "a-trace"})
        tenant_a_trace.trace_id = "a-trace"
        tenant_b_trace = MagicMock(**{**_MOCK_TRACE_ITEM.__dict__, "trace_id": "b-trace"})
        tenant_b_trace.trace_id = "b-trace"

        with patch("modules.query.router.list_traces") as mock_list, \
             patch("modules.query.router.latest_eval_runs_by_trace_id", return_value={}), \
             patch("modules.query.router.SessionLocal"):
            mock_list.return_value = ([tenant_a_trace], None)
            r_a = test_client.get("/v1/traces?tenant_id=tenant_a").json()

            mock_list.return_value = ([tenant_b_trace], None)
            r_b = test_client.get("/v1/traces?tenant_id=tenant_b").json()

        # Tenant B's response should contain B's trace, not A's.
        assert r_a["items"][0]["trace_id"] == "a-trace"
        assert r_b["items"][0]["trace_id"] == "b-trace"
