"""Eval execution, insights, and regression batch APIs."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from db.repository import (
    compute_eval_insights_summary,
    create_eval_run_group,
    create_eval_run_queued,
    list_recent_trace_ids,
    summarize_eval_run_group,
    trace_has_any_span,
)
from db.session import SessionLocal
from modules.evaluation.schemas import (
    EvalRunGroupDetailOut,
    EvalRunOut,
    FailureTypeCountOut,
    InsightsSummaryOut,
    RegressionRunIn,
    RegressionRunQueuedOut,
    WorstRegressionOut,
)
from modules.jobs import EVAL_RUN_JOB, enqueue_job, stable_job_id

router = APIRouter(tags=["evaluation"])


@router.post("/v1/traces/{trace_id}/evals/run")
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
    from rq.job import Retry

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
        jid = stable_job_id("eval_run", "v1", str(run.id), trace_id, eval_name)
        retry = Retry(max=5, interval=[10, 30, 60, 120, 300])
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


@router.get("/v1/insights/summary", response_model=InsightsSummaryOut)
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


@router.get("/v1/eval-run-groups/{group_id}", response_model=EvalRunGroupDetailOut)
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


@router.post("/v1/regression/run", response_model=RegressionRunQueuedOut)
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
