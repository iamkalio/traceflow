"""Read routes for traces and spans."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from db.repository import (
    latest_eval_runs_by_trace_id,
    list_eval_results_for_trace,
    list_eval_runs_for_trace,
    list_eval_runs_recent,
    list_spans_for_trace,
    list_traces,
    trace_has_any_span,
)
from db.session import SessionLocal
from modules.cache import get_cache
from modules.cache.decorators import cache_aside
from modules.cache.keys import eval_results_key, trace_detail_key, trace_list_cursor_key
from modules.cache.ttl import (
    EVAL_RESULTS_TTL_S,
    TRACE_DETAIL_TTL_S,
    TRACE_LIST_TTL_S,
    jittered_ttl,
)
from modules.evaluation.schemas import EvalResultOut, EvalRunOut
from modules.query.schemas import TraceListResponse, TraceSpanOut

router = APIRouter(tags=["query"])


@router.get("/v1/traces", response_model=TraceListResponse)
async def list_traces_api(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: datetime | None = Query(default=None, description="Return traces with last_seen < cursor (RFC3339 datetime)."),
    q: str | None = Query(default=None, description="Case-insensitive search over span name/prompt/completion."),
    status: str | None = Query(default=None, description="Filter by span status (e.g. success/error)."),
    model: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> TraceListResponse:
    # Build a cache key that includes ALL query parameters.  If any single
    # parameter changes, a different key is produced, so different filter
    # combinations never share a cache slot.
    key = trace_list_cursor_key(
        tenant_id=tenant_id,
        cursor=cursor,
        limit=limit,
        q=q,
        status=status,
        model=model,
        start_time=start_time,
        end_time=end_time,
    )

    def _compute() -> dict:
        # This runs only on a cache miss.  We build the response dict here
        # (rather than a Pydantic object) so that the cached value is a plain
        # JSON-safe dict — compatible with both InMemoryCache (stores Python
        # objects) and RedisCache (serialises to JSON).  Pydantic's
        # model_dump(mode="json") converts datetime fields to ISO strings,
        # which Redis can round-trip without information loss.
        session = SessionLocal()
        try:
            items, next_cursor = list_traces(
                session,
                limit=limit,
                cursor=cursor,
                q=q,
                status=status,
                model=model,
                tenant_id=tenant_id,
                start_time=start_time,
                end_time=end_time,
            )
            trace_ids = [i.trace_id for i in items]
            latest_runs = latest_eval_runs_by_trace_id(session, trace_ids)

            response = TraceListResponse(
                items=[
                    {
                        "trace_id": i.trace_id,
                        "name": i.name,
                        "input": i.input,
                        "output": i.output,
                        "annotations": i.annotations,
                        "eval_status": (r.status if (r := latest_runs.get(i.trace_id)) else "pending"),
                        "eval_score": (r.score if r else None),
                        "eval_label": (r.label if r else None),
                        "start_time": i.start_time,
                        "latency_ms": i.latency_ms,
                        "first_seen": i.first_seen,
                        "last_seen": i.last_seen,
                        "span_count": i.span_count,
                        "status": i.status,
                        "total_tokens": i.total_tokens,
                        "total_cost_usd": i.total_cost_usd,
                    }
                    for i in items
                ],
                next_cursor=(next_cursor.isoformat() if next_cursor else None),
            )
            # mode="json" ensures datetime fields become ISO strings so the
            # dict is safe to store in Redis (which serialises with json.dumps).
            return response.model_dump(mode="json")
        finally:
            session.close()

    cached = cache_aside(get_cache(), key, _compute, ttl_s=jittered_ttl(TRACE_LIST_TTL_S))
    # Reconstruct the Pydantic model from the cached dict.  model_validate()
    # coerces ISO strings back to datetime objects where the schema expects them.
    return TraceListResponse.model_validate(cached)


@router.get("/v1/traces/{trace_id}", response_model=list[TraceSpanOut])
async def get_trace_detail(trace_id: str) -> list[TraceSpanOut]:
    # trace_detail_key is scoped to trace_id only — trace spans are immutable
    # after ingest, so this entry has a long TTL (TRACE_DETAIL_TTL_S = 5 min).
    key = trace_detail_key(trace_id)

    def _compute() -> list[dict] | None:
        # Returns None when the trace does not exist so we can raise 404.
        # cache_aside stores None as the _CACHED_NONE sentinel, preventing
        # repeated DB hits for non-existent trace IDs.
        session = SessionLocal()
        try:
            if not trace_has_any_span(session, trace_id):
                return None  # will be stored as _CACHED_NONE
            spans = list_spans_for_trace(session, trace_id)
            return [TraceSpanOut.model_validate(s).model_dump(mode="json") for s in spans]
        finally:
            session.close()

    cached = cache_aside(get_cache(), key, _compute, ttl_s=jittered_ttl(TRACE_DETAIL_TTL_S))

    if cached is None:
        # Either a genuine miss from DB (trace doesn't exist) or the cached
        # result of a previous 404.  Either way, raise 404.
        raise HTTPException(status_code=404, detail="trace not found")

    return [TraceSpanOut.model_validate(d) for d in cached]


@router.get("/v1/traces/{trace_id}/evals", response_model=list[EvalResultOut])
async def list_trace_evals(
    trace_id: str,
    eval_name: str | None = Query(default=None, description="Filter by eval_name, e.g. groundedness"),
) -> list[EvalResultOut]:
    """Return all eval rows for this W3C trace_id (all spans). Empty list if none yet.
    404 if no spans exist for trace_id (unknown trace).
    """
    # Scope the key to both trace_id and eval_name so that different
    # evaluators have independent cache slots.  eval_name=None ("all evals")
    # gets its own slot too, distinct from any named evaluator.
    key = eval_results_key(trace_id, eval_name)

    def _compute() -> list[dict] | None:
        session = SessionLocal()
        try:
            if not trace_has_any_span(session, trace_id):
                return None  # 404 — cached as _CACHED_NONE
            rows = list_eval_results_for_trace(session, trace_id, eval_name=eval_name)
            return [EvalResultOut.model_validate(r).model_dump(mode="json") for r in rows]
        finally:
            session.close()

    cached = cache_aside(get_cache(), key, _compute, ttl_s=jittered_ttl(EVAL_RESULTS_TTL_S))

    if cached is None:
        raise HTTPException(status_code=404, detail="trace not found")

    return [EvalResultOut.model_validate(d) for d in cached]


@router.get("/v1/traces/{trace_id}/eval-runs", response_model=list[EvalRunOut])
async def list_trace_eval_runs(trace_id: str) -> list[EvalRunOut]:
    # Eval runs change state frequently (queued → running → completed), so
    # we deliberately do NOT cache this endpoint.  Clients polling for job
    # status need real-time data.  If this endpoint becomes a hotspot later,
    # a very short TTL (5s) would be appropriate.
    session = SessionLocal()
    try:
        if not trace_has_any_span(session, trace_id):
            raise HTTPException(status_code=404, detail="trace not found")
        rows = list_eval_runs_for_trace(session, trace_id)
        return [EvalRunOut.model_validate(r) for r in rows]
    finally:
        session.close()


@router.get("/v1/eval-runs", response_model=list[EvalRunOut])
async def list_eval_runs_api(
    limit: int = Query(default=100, ge=1, le=500),
    trace_id: str | None = Query(default=None, description="Only runs for this trace_id"),
) -> list[EvalRunOut]:
    """Recent LLM-as-a-judge (and other) eval runs across traces."""
    # Not cached — same reason as list_trace_eval_runs above.  Eval run
    # status transitions happen frequently and clients expect near-real-time
    # updates.
    session = SessionLocal()
    try:
        rows = list_eval_runs_recent(session, limit=limit, trace_id=trace_id)
        return [EvalRunOut.model_validate(r) for r in rows]
    finally:
        session.close()
