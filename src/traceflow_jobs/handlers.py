from __future__ import annotations

import logging

from rq import get_current_job

from db.models import EvalRun
from db.repository import (
    list_spans_for_trace,
    set_eval_run_completed,
    set_eval_run_failed,
    set_eval_run_running,
    set_eval_run_skipped,
    update_eval_run_span_id,
)
from db.session import SessionLocal
from services.evals.groundedness_eval import run_groundedness_span_eval
from services.evals.llm_groundedness_judge import is_transient_openai_error
from services.evals.regression_compare_eval import run_regression_compare_span_eval

logger = logging.getLogger(__name__)


def _normalize_evaluator_type(raw: str | None) -> str:
    return (raw or "").strip().lower()


def ping_job(msg: str = "ping") -> str:
    logger.info("ping_job: %s", msg)
    return msg


def eval_span_job(trace_id: str, span_id: str) -> str:
    """RQ processor: session + delegate to background service."""
    job = get_current_job()
    job_id = job.id if job is not None else None
    session = SessionLocal()
    try:
        out, _ = run_groundedness_span_eval(session, trace_id, span_id)
        return out
    except Exception:
        logger.exception(
            "eval_span_job failed job_id=%s trace_id=%s span_id=%s",
            job_id,
            trace_id,
            span_id,
        )
        session.rollback()
        raise
    finally:
        session.close()


def eval_run_job(eval_run_id: int, openai_api_key: str) -> str:
    """
    eval_runs: queued -> running -> completed / skipped / failed.
    ``openai_api_key`` is supplied per request (browser header); not read from the database.
    """
    job = get_current_job()
    job_id = job.id if job is not None else None
    session = SessionLocal()
    try:
        run = session.get(EvalRun, eval_run_id)
        if run is None:
            logger.warning("eval_run_job: no EvalRun id=%s job_id=%s", eval_run_id, job_id)
            return "missing"

        api_key = (openai_api_key or "").strip()
        if not api_key:
            set_eval_run_failed(session, eval_run_id, error="No OpenAI API key provided to worker")
            return "ok"

        set_eval_run_running(session, eval_run_id)

        trace_id = run.trace_id
        span_id = (run.span_id or "").strip()
        if not span_id:
            spans = list_spans_for_trace(session, trace_id)
            if not spans:
                set_eval_run_failed(session, eval_run_id, error="Trace has no spans")
                return "ok"
            span_id = spans[-1].span_id
            update_eval_run_span_id(session, eval_run_id, span_id)

        etype = _normalize_evaluator_type(run.evaluator_type)
        is_groundedness = etype.startswith("groundedness")
        is_regression = etype.startswith("regression_compare")
        if is_groundedness:
            outcome, detail = run_groundedness_span_eval(
                session, trace_id, span_id, openai_api_key=api_key
            )
        elif is_regression:
            outcome, detail = run_regression_compare_span_eval(
                session, trace_id, span_id, eval_run_id, openai_api_key=api_key
            )
        else:
            set_eval_run_failed(
                session,
                eval_run_id,
                error=(
                    f"Unknown evaluator_type: {run.evaluator_type!r}. "
                    "Supported: groundedness*, regression_compare*. "
                    "If you use regression batches, redeploy the RQ worker from the same image/commit as the API "
                    "so eval_run_job includes the regression_compare branch."
                ),
            )
            return "ok"

        if outcome == "not_found":
            set_eval_run_failed(session, eval_run_id, error="Span not found for trace")
            return "ok"
        if not detail:
            set_eval_run_failed(session, eval_run_id, error="Eval produced no detail")
            return "ok"

        kind = detail.get("kind")
        if kind == "completed":
            if is_regression and not detail.get("regression_baseline_only"):
                extra_ctx: dict[str, object] = {
                    "snapshot_input": str(detail.get("snapshot_input") or "")[:50_000],
                    "snapshot_output": str(detail.get("snapshot_output") or "")[:50_000],
                    "eval_kind": "regression_compare",
                    "prompt_improvement": "",
                    "context_improvement": "",
                    "failure_type": "",
                    "suggested_fix": "",
                }
                if detail.get("previous_eval_run_id") is not None:
                    extra_ctx["previous_eval_run_id"] = detail["previous_eval_run_id"]
                if detail.get("previous_score") is not None:
                    extra_ctx["previous_score"] = detail["previous_score"]
                if detail.get("current_score") is not None:
                    extra_ctx["current_score"] = detail["current_score"]
                if detail.get("delta_score") is not None:
                    extra_ctx["delta_score"] = detail["delta_score"]
                extra_ctx["verdict"] = str(detail.get("label") or "")
                extra_ctx["regression_compare_score"] = detail.get("score")
            else:
                extra_ctx = {
                    "prompt_improvement": str(detail.get("prompt_improvement") or ""),
                    "context_improvement": str(detail.get("context_improvement") or ""),
                    "failure_type": str(detail.get("failure_type") or ""),
                    "suggested_fix": str(detail.get("suggested_fix") or ""),
                    "snapshot_input": str(detail.get("snapshot_input") or "")[:50_000],
                    "snapshot_output": str(detail.get("snapshot_output") or "")[:50_000],
                }
                # Groundedness-scale score for this span (delta vs prior uses this across runs).
                if detail.get("score") is not None and not is_regression:
                    extra_ctx["current_score"] = detail.get("score")
                if is_regression and detail.get("regression_baseline_only"):
                    extra_ctx["eval_kind"] = "regression_baseline_capture"
                    extra_ctx["regression_note"] = (
                        "No prior eval output to compare yet. Groundedness ran to capture a baseline snapshot; "
                        "run regression again after outputs change to measure improved/regressed/unchanged."
                    )
                    if detail.get("score") is not None:
                        extra_ctx["current_score"] = detail.get("score")
                    extra_ctx["verdict"] = "baseline_capture"
                    extra_ctx["previous_score"] = None
                    extra_ctx["delta_score"] = None
            set_eval_run_completed(
                session,
                eval_run_id,
                score=detail.get("score"),
                label=str(detail.get("label") or ""),
                reasoning=str(detail.get("reason") or ""),
                latency_ms=detail.get("latency_ms"),
                cost_usd=detail.get("cost_usd"),
                extra_context=extra_ctx,
            )
        elif kind == "skipped":
            set_eval_run_skipped(
                session, eval_run_id, reasoning=str(detail.get("reason") or "skipped")
            )
        elif kind == "error":
            set_eval_run_failed(session, eval_run_id, error=str(detail.get("reason") or "error"))
        else:
            set_eval_run_failed(session, eval_run_id, error=f"Unexpected eval detail kind: {kind!r}")
        return "ok"
    except Exception as e:
        session.rollback()
        if is_transient_openai_error(e):
            logger.warning(
                "eval_run_job transient OpenAI error job_id=%s eval_run_id=%s: %s",
                job_id,
                eval_run_id,
                e,
            )
            raise
        logger.exception("eval_run_job failed job_id=%s eval_run_id=%s", job_id, eval_run_id)
        try:
            set_eval_run_failed(session, eval_run_id, error=str(e))
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()
