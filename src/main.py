import logging
import asyncio
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from db.repository import (
    compute_eval_insights_summary,
    create_eval_run_group,
    create_eval_run_queued,
    get_trace_list_items_by_ids,
    latest_eval_runs_by_trace_id,
    list_spans_for_trace,
    list_eval_results_for_trace,
    list_eval_runs_for_trace,
    list_eval_runs_recent,
    list_recent_trace_ids,
    list_traces,
    persist_normalized_events,
    summarize_eval_run_group,
    trace_has_any_span,
)
from db.session import SessionLocal
from otlp_ingest import ingest_otlp_body
from traceflow_jobs import EVAL_RUN_JOB, enqueue_job, stable_job_id
from schemas import (
    EvalResultOut,
    EvalRunGroupDetailOut,
    EvalRunOut,
    FailureTypeCountOut,
    InsightsSummaryOut,
    RegressionRunIn,
    RegressionRunQueuedOut,
    TraceListResponse,
    TraceSpanOut,
    WorstRegressionOut,
)
from ws.traces import trace_ws_manager

logger = logging.getLogger(__name__)

app = FastAPI(title="Traceflow OTLP Ingest", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.websocket("/v1/ws/traces")
async def ws_traces(ws: WebSocket) -> None:
    await trace_ws_manager.connect(ws)
    try:
        # Keep connection alive; we don't require client messages.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await trace_ws_manager.disconnect(ws)
    except Exception:
        await trace_ws_manager.disconnect(ws)


@app.post("/v1/traces")
async def otlp_traces_ingest(request: Request) -> list[dict]:
    """
    SDK → parse OTLP protobuf → normalize → store in PostgreSQL.
    Returns a JSON array of normalized LLM events for this request.
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")
    try:
        events = ingest_otlp_body(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    session = SessionLocal()
    try:
        inserted = persist_normalized_events(session, events)
        # Broadcast newly inserted/updated traces to websocket subscribers.
        if inserted:
            trace_ids = sorted({tid for tid, _sid in inserted})
            live_items = get_trace_list_items_by_ids(session, trace_ids)
            latest_runs = latest_eval_runs_by_trace_id(session, [i.trace_id for i in live_items])

            async def _broadcast() -> None:
                for item in live_items:
                    r = latest_runs.get(item.trace_id)
                    await trace_ws_manager.broadcast(
                        {
                            "type": "trace.upsert",
                            "item": {
                                "trace_id": item.trace_id,
                                "name": item.name,
                                "input": item.input,
                                "output": item.output,
                                "annotations": item.annotations,
                                "eval_status": (r.status if r else "pending"),
                                "eval_score": (r.score if r else None),
                                "eval_label": (r.label if r else None),
                                "start_time": item.start_time,
                                "latency_ms": item.latency_ms,
                                "first_seen": item.first_seen,
                                "last_seen": item.last_seen,
                                "span_count": item.span_count,
                                "status": item.status,
                                "total_tokens": item.total_tokens,
                                "total_cost_usd": item.total_cost_usd,
                            },
                        }
                    )

            asyncio.create_task(_broadcast())
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info("otlp v1 traces: batch %d events, %d inserted spans", len(events), len(inserted))
    return [e.model_dump() for e in events]


@app.get("/v1/traces", response_model=TraceListResponse)
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


@app.get("/v1/traces/{trace_id}", response_model=list[TraceSpanOut])
async def get_trace_detail(trace_id: str) -> list[TraceSpanOut]:
    session = SessionLocal()
    try:
        if not trace_has_any_span(session, trace_id):
            raise HTTPException(status_code=404, detail="trace not found")
        spans = list_spans_for_trace(session, trace_id)
        return [TraceSpanOut.model_validate(s) for s in spans]
    finally:
        session.close()


@app.get("/v1/traces/{trace_id}/evals", response_model=list[EvalResultOut])
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


@app.get("/v1/traces/{trace_id}/eval-runs", response_model=list[EvalRunOut])
async def list_trace_eval_runs(trace_id: str) -> list[EvalRunOut]:
    session = SessionLocal()
    try:
        if not trace_has_any_span(session, trace_id):
            raise HTTPException(status_code=404, detail="trace not found")
        rows = list_eval_runs_for_trace(session, trace_id)
        return [EvalRunOut.model_validate(r) for r in rows]
    finally:
        session.close()


@app.get("/v1/eval-runs", response_model=list[EvalRunOut])
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


@app.post("/v1/traces/{trace_id}/evals/run")
async def run_trace_eval(
    trace_id: str,
    payload: dict,
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
) -> dict:
    """
    Queue an eval run. Pass the OpenAI API key in the ``X-OpenAI-API-Key`` header
    (browser stores it in localStorage; the server does not persist keys).
    The key is sent to the worker only inside the RQ job payload until the job finishes.
    """
    eval_name = str(payload.get("eval_name") or "groundedness_v1")
    key = (x_openai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Missing X-OpenAI-API-Key header (set your key in Settings and run eval from the UI).",
        )
    session = SessionLocal()
    try:
        if not trace_has_any_span(session, trace_id):
            raise HTTPException(status_code=404, detail="trace not found")

        run = create_eval_run_queued(
            session,
            trace_id=trace_id,
            span_id=None,
            tenant_id=None,
            evaluator_type=eval_name,
            evaluator_version="v1",
        )
        from rq.job import Retry

        jid = stable_job_id("eval_run", "v1", str(run.id), trace_id, eval_name)
        retry = Retry(max=5, interval=[10, 30, 60, 120, 300])
        # Safe RQ log line — never put the API key in ``description`` (default would stringify kwargs).
        safe_rq_description = (
            f"eval_run_job(eval_run_id={run.id}, trace_id={trace_id}, evaluator={eval_name})"
        )
        enqueue_job(
            EVAL_RUN_JOB,
            job_id=jid,
            kwargs={"eval_run_id": run.id, "openai_api_key": key},
            retry=retry,
            description=safe_rq_description,
        )
        return {"status": "queued", "eval_run_id": run.id}
    finally:
        session.close()


@app.get("/v1/insights/summary", response_model=InsightsSummaryOut)
async def insights_summary(
    limit: int = Query(default=100, ge=1, le=500, description="Recent eval runs to include"),
) -> InsightsSummaryOut:
    """Rollups for the Insights page: score mix, failure types, eval spend."""
    session = SessionLocal()
    try:
        raw = compute_eval_insights_summary(session, limit=limit)
        return InsightsSummaryOut(
            sample_size=raw["sample_size"],
            completed_with_score=raw["completed_with_score"],
            avg_score=raw["avg_score"],
            good_count=raw["good_count"],
            borderline_count=raw["borderline_count"],
            bad_count=raw["bad_count"],
            good_pct=raw["good_pct"],
            borderline_pct=raw["borderline_pct"],
            bad_pct=raw["bad_pct"],
            total_eval_cost_usd=raw["total_eval_cost_usd"],
            top_failure_types=[FailureTypeCountOut(**x) for x in raw["top_failure_types"]],
        )
    finally:
        session.close()


@app.get("/v1/eval-run-groups/{group_id}", response_model=EvalRunGroupDetailOut)
async def get_eval_run_group_detail(group_id: int) -> EvalRunGroupDetailOut:
    """Regression / batch group with aggregate scores and per-trace eval rows."""
    session = SessionLocal()
    try:
        raw = summarize_eval_run_group(session, group_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="eval run group not found")
        return EvalRunGroupDetailOut(
            id=raw["id"],
            name=raw["name"],
            status=raw["status"],
            total_jobs=raw["total_jobs"],
            tenant_id=raw["tenant_id"],
            created_at=raw["created_at"],
            avg_score=raw["avg_score"],
            good_count=raw["good_count"],
            borderline_count=raw["borderline_count"],
            bad_count=raw["bad_count"],
            good_pct=raw["good_pct"],
            borderline_pct=raw["borderline_pct"],
            bad_pct=raw["bad_pct"],
            total_eval_cost_usd=raw["total_eval_cost_usd"],
            completed_jobs=raw["completed_jobs"],
            top_failure_types=[FailureTypeCountOut(**x) for x in raw["top_failure_types"]],
            eval_runs=[EvalRunOut.model_validate(r) for r in raw["runs"]],
            pct_improved=raw.get("pct_improved"),
            pct_regressed=raw.get("pct_regressed"),
            pct_unchanged=raw.get("pct_unchanged"),
            avg_delta_score=raw.get("avg_delta_score"),
            worst_regressions=[
                WorstRegressionOut(**x) for x in raw.get("worst_regressions", [])
            ],
            regression_summary=raw.get("regression_summary") or "",
        )
    finally:
        session.close()


@app.post("/v1/regression/run", response_model=RegressionRunQueuedOut)
async def run_regression(
    payload: RegressionRunIn,
    x_openai_api_key: str | None = Header(None, alias="X-OpenAI-API-Key"),
) -> RegressionRunQueuedOut:
    """
    Queue **regression compare** jobs: same RQ entrypoint as single-trace evals (``eval_run_job``), with
    ``evaluator_type=regression_compare_v1``. Compares current span output to the prior eval snapshot.
    """
    from rq.job import Retry

    key = (x_openai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Missing X-OpenAI-API-Key header (set your key in Settings and run from the UI).",
        )
    eval_name = str(payload.eval_name or "regression_compare_v1").strip() or "regression_compare_v1"
    n = int(payload.n)
    session = SessionLocal()
    try:
        trace_ids = list_recent_trace_ids(session, limit=n)
        if not trace_ids:
            raise HTTPException(status_code=400, detail="No traces to evaluate yet.")
        group = create_eval_run_group(
            session,
            name=f"regression_compare_last_{len(trace_ids)}_traces",
            total_jobs=len(trace_ids),
            tenant_id=None,
        )
        eval_run_ids: list[int] = []
        retry = Retry(max=5, interval=[10, 30, 60, 120, 300])
        for tid in trace_ids:
            run = create_eval_run_queued(
                session,
                trace_id=tid,
                span_id=None,
                tenant_id=None,
                evaluator_type=eval_name,
                evaluator_version="v1",
                group_id=group.id,
            )
            eval_run_ids.append(run.id)
            jid = stable_job_id(
                "eval_run", "v1", str(run.id), tid, eval_name, str(group.id), "regression"
            )
            safe_rq_description = (
                f"eval_run_job(eval_run_id={run.id}, trace_id={tid}, "
                f"evaluator={eval_name}, group_id={group.id})"
            )
            enqueue_job(
                EVAL_RUN_JOB,
                job_id=jid,
                kwargs={"eval_run_id": run.id, "openai_api_key": key},
                retry=retry,
                description=safe_rq_description,
            )
        return RegressionRunQueuedOut(status="queued", group_id=group.id, eval_run_ids=eval_run_ids)
    finally:
        session.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
