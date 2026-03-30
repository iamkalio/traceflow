from __future__ import annotations

import logging
import os
import traceback
from typing import Any, Literal

from sqlalchemy.orm import Session

from db.repository import fetch_trace_by_span, insert_eval_result_idempotent
from services.evals.context_resolution import extract_context_for_eval
from services.evals.llm_groundedness_judge import (
    GroundednessParseError,
    call_groundedness_judge,
    is_transient_openai_error,
)

logger = logging.getLogger(__name__)

# Stored in eval_results; bump version when judge prompt/schema changes.
GROUNDEDNESS_EVAL_NAME = "groundedness"
GROUNDEDNESS_EVAL_VERSION = "v1"

GroundednessOutcome = Literal["ok", "not_found"]

_RAW_PREVIEW_LIMIT = 8000


def run_groundedness_span_eval(
    session: Session,
    trace_id: str,
    span_id: str,
    *,
    openai_api_key: str | None = None,
) -> tuple[GroundednessOutcome, dict[str, Any] | None]:
    """
    Run groundedness for a single span. Returns (outcome, detail) where detail is
    used by eval_run_job to update eval_runs (completed / skipped / error).
    """
    row = fetch_trace_by_span(session, trace_id, span_id)
    if row is None:
        logger.warning(
            "run_groundedness_span_eval: no trace for trace_id=%s span_id=%s",
            trace_id,
            span_id,
        )
        return "not_found", None

    if (row.status or "").lower() == "error":
        insert_eval_result_idempotent(
            session,
            trace_id=row.trace_id,
            span_id=row.span_id,
            eval_name=GROUNDEDNESS_EVAL_NAME,
            eval_version=GROUNDEDNESS_EVAL_VERSION,
            score=None,
            label="skipped",
            reason="Trace status is error; groundedness skipped.",
            details={"trace_pk": row.id, "status": row.status},
        )
        session.commit()
        return "ok", {"kind": "skipped", "reason": "Trace status is error; groundedness skipped."}

    ctx_text = extract_context_for_eval(row)
    context_block = (
        ctx_text
        if ctx_text
        else "(No retrieval context was recorded for this span. "
        "Judge conservatively: factual claims cannot be verified without context.)"
    )
    question_text = (row.prompt or "").strip() or "(no user question captured)"
    completion_text = (row.completion or "").strip() or "(empty)"

    if not (openai_api_key or "").strip() and not os.environ.get("OPENAI_API_KEY"):
        insert_eval_result_idempotent(
            session,
            trace_id=row.trace_id,
            span_id=row.span_id,
            eval_name=GROUNDEDNESS_EVAL_NAME,
            eval_version=GROUNDEDNESS_EVAL_VERSION,
            score=None,
            label="skipped",
            reason="OPENAI_API_KEY is not set; groundedness not run.",
            details={
                "trace_pk": row.id,
                "had_context": bool(ctx_text),
                "context_chars": len(ctx_text) if ctx_text else 0,
            },
        )
        session.commit()
        return "ok", {"kind": "skipped", "reason": "No OpenAI API key configured (env or BYOK)."}

    try:
        judge = call_groundedness_judge(
            question=question_text,
            context=context_block,
            response=completion_text,
            api_key=(openai_api_key.strip() if openai_api_key else None),
        )
    except GroundednessParseError as e:
        raw = e.raw_content or ""
        logger.warning(
            "groundedness parse failure trace_id=%s span_id=%s: %s",
            trace_id,
            span_id,
            e,
        )
        insert_eval_result_idempotent(
            session,
            trace_id=row.trace_id,
            span_id=row.span_id,
            eval_name=GROUNDEDNESS_EVAL_NAME,
            eval_version=GROUNDEDNESS_EVAL_VERSION,
            score=None,
            label="error",
            reason=str(e)[:2000],
            details={
                "trace_pk": row.id,
                "error_kind": "parse",
                "raw_model_response": raw[:_RAW_PREVIEW_LIMIT],
                "raw_truncated": len(raw) > _RAW_PREVIEW_LIMIT,
                "parse_error": repr(e.cause) if e.cause else None,
                "had_context": bool(ctx_text),
            },
        )
        session.commit()
        return "ok", {"kind": "error", "reason": str(e)[:2000]}
    except Exception as e:
        if is_transient_openai_error(e):
            logger.warning(
                "groundedness transient OpenAI error trace_id=%s span_id=%s (job will retry): %s",
                trace_id,
                span_id,
                e,
            )
            raise
        logger.exception(
            "groundedness judge failed trace_id=%s span_id=%s",
            trace_id,
            span_id,
        )
        insert_eval_result_idempotent(
            session,
            trace_id=row.trace_id,
            span_id=row.span_id,
            eval_name=GROUNDEDNESS_EVAL_NAME,
            eval_version=GROUNDEDNESS_EVAL_VERSION,
            score=None,
            label="error",
            reason=str(e)[:2000],
            details={
                "trace_pk": row.id,
                "error_kind": "judge",
                "exception_type": type(e).__name__,
                "traceback": traceback.format_exc()[-8000:],
                "had_context": bool(ctx_text),
            },
        )
        session.commit()
        return "ok", {"kind": "error", "reason": str(e)[:2000]}

    raw_full = judge.raw_response
    insert_eval_result_idempotent(
        session,
        trace_id=row.trace_id,
        span_id=row.span_id,
        eval_name=GROUNDEDNESS_EVAL_NAME,
        eval_version=GROUNDEDNESS_EVAL_VERSION,
        score=judge.output.score,
        label=judge.output.label,
        reason=judge.output.reason,
        details={
            "trace_pk": row.id,
            "model_judge": True,
            "trace_model": row.model,
            "had_context": bool(ctx_text),
            "context_chars": len(ctx_text) if ctx_text else 0,
            "prompt_preview": (row.prompt or "")[:500],
            "raw_model_response": raw_full[:_RAW_PREVIEW_LIMIT],
            "raw_truncated": len(raw_full) > _RAW_PREVIEW_LIMIT,
        },
    )
    session.commit()
    logger.info(
        "run_groundedness_span_eval: trace_id=%s span_id=%s score=%s label=%s",
        trace_id,
        span_id,
        judge.output.score,
        judge.output.label,
    )
    return "ok", {
        "kind": "completed",
        "score": judge.output.score,
        "label": judge.output.label,
        "reason": judge.output.reason,
        "prompt_improvement": judge.output.prompt_improvement,
        "context_improvement": judge.output.context_improvement,
        "failure_type": judge.output.failure_type,
        "suggested_fix": judge.output.suggested_fix,
        "cost_usd": judge.cost_usd,
        "latency_ms": judge.latency_ms,
        "snapshot_input": ((row.prompt or "")[:50_000]),
        "snapshot_output": ((row.completion or "")[:50_000]),
    }
