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
        return TraceListResponse(
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
    finally:
        session.close()


@router.get("/v1/traces/{trace_id}", response_model=list[TraceSpanOut])
async def get_trace_detail(trace_id: str) -> list[TraceSpanOut]:
    session = SessionLocal()
    try:
        if not trace_has_any_span(session, trace_id):
            raise HTTPException(status_code=404, detail="trace not found")
        spans = list_spans_for_trace(session, trace_id)
        return [TraceSpanOut.model_validate(s) for s in spans]
    finally:
        session.close()


@router.get("/v1/traces/{trace_id}/evals", response_model=list[EvalResultOut])
async def list_trace_evals(
    trace_id: str,
    eval_name: str | None = Query(default=None, description="Filter by eval_name, e.g. groundedness"),
) -> list[EvalResultOut]:
    """
    Return all eval rows for this W3C trace_id (all spans). Empty list if none yet.
    404 if no spans exist for trace_id (unknown trace).
    """
    session = SessionLocal()
    try:
        if not trace_has_any_span(session, trace_id):
            raise HTTPException(status_code=404, detail="trace not found")
        rows = list_eval_results_for_trace(session, trace_id, eval_name=eval_name)
        return [EvalResultOut.model_validate(r) for r in rows]
    finally:
        session.close()


@router.get("/v1/traces/{trace_id}/eval-runs", response_model=list[EvalRunOut])
async def list_trace_eval_runs(trace_id: str) -> list[EvalRunOut]:
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
    session = SessionLocal()
    try:
        rows = list_eval_runs_recent(session, limit=limit, trace_id=trace_id)
        return [EvalRunOut.model_validate(r) for r in rows]
    finally:
        session.close()
