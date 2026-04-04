from __future__ import annotations

import logging

from rq import get_current_job

from db.models import EvalRun
from db.repositories.evaluation_repository import (
    set_eval_run_failed,
    set_eval_run_running,
    update_eval_run_span_id,
)
from db.repositories.trace_repository import list_spans_for_trace
from db.session import SessionLocal
from modules.evaluation.domain.evaluator import evaluator_family, normalize_evaluator_type
from modules.evaluation.engine.groundedness_eval import run_groundedness_span_eval
from modules.evaluation.engine.llm_groundedness_judge import is_transient_openai_error
from modules.evaluation.engine.regression_compare_eval import run_regression_compare_span_eval
from modules.jobs.orchestration.eval_pipeline import finalize_eval_run_from_engine_detail

logger = logging.getLogger(__name__)


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

        etype = normalize_evaluator_type(run.evaluator_type)
        family = evaluator_family(etype)
        if family == "groundedness":
            outcome, detail = run_groundedness_span_eval(
                session, trace_id, span_id, openai_api_key=api_key
            )
        elif family == "regression_compare":
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

        finalize_eval_run_from_engine_detail(
            session,
            eval_run_id=eval_run_id,
            evaluator_type_raw=run.evaluator_type,
            outcome=outcome,
            detail=detail,
        )
        try:
            from core.metrics import GLOBAL_METRICS

            if outcome == "not_found":
                GLOBAL_METRICS.record_eval_terminal(failed=True)
            elif detail and detail.get("latency_ms") is not None:
                GLOBAL_METRICS.observe_eval_latency_ms(float(detail["latency_ms"]))
                kind = detail.get("kind")
                if kind == "completed":
                    GLOBAL_METRICS.record_eval_terminal(failed=False)
                elif kind == "error":
                    GLOBAL_METRICS.record_eval_terminal(failed=True)
        except ImportError:
            pass
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
