"""Regression compare: previous vs current span output using a dedicated judge (see regression_compare_judge)."""

from __future__ import annotations

import logging
import os
import traceback
from typing import Any, Literal

from sqlalchemy.orm import Session

from db.models import EvalRun
from db.repository import fetch_trace_by_span, get_prior_completed_eval_run
from modules.context.extractor import extract_context_for_eval
from modules.evaluation.engine.groundedness_eval import run_groundedness_span_eval
from modules.evaluation.engine.regression_compare_judge import (
    RegressionCompareParseError,
    call_regression_compare_judge,
)
from modules.evaluation.engine.llm_groundedness_judge import is_transient_openai_error

logger = logging.getLogger(__name__)

_PREVIEW = 14_000

GroundednessOutcome = Literal["ok", "not_found"]


def _snapshot_output_from_eval_run(prior: EvalRun) -> str | None:
    ctx = prior.context if isinstance(prior.context, dict) else {}
    snap = ctx.get("snapshot_output")
    if isinstance(snap, str) and snap.strip():
        return snap.strip()
    if prior.output and str(prior.output).strip():
        return str(prior.output).strip()
    return None


def _prior_groundedness_score(prior: EvalRun) -> float | None:
    """Best-effort groundedness-scale score from the prior eval (for delta vs current groundedness)."""
    ctx = prior.context if isinstance(prior.context, dict) else {}
    cs = ctx.get("current_score")
    if isinstance(cs, (int, float)):
        return float(cs)
    et = (prior.evaluator_type or "").strip().lower()
    if et.startswith("groundedness") and prior.score is not None:
        return float(prior.score)
    if ctx.get("eval_kind") == "regression_baseline_capture" and prior.score is not None:
        return float(prior.score)
    return None


def run_regression_compare_span_eval(
    session: Session,
    trace_id: str,
    span_id: str,
    eval_run_id: int,
    *,
    openai_api_key: str | None = None,
) -> tuple[GroundednessOutcome, dict[str, Any] | None]:
    """
    Compare the latest span completion (current) to the snapshot from the prior completed eval_run
    (previous). Requires a prior eval with stored snapshot_output (from groundedness) or output column.

    Full compare path: (1) regression judge: verdict + score in [-1,1]; (2) groundedness on current output
    for previous_score / current_score / delta_score on a 0–1 scale.
    """
    row = fetch_trace_by_span(session, trace_id, span_id)
    if row is None:
        return "not_found", None

    if (row.status or "").lower() == "error":
        return "ok", {"kind": "skipped", "reason": "Trace span status is error; regression compare skipped."}

    prior = get_prior_completed_eval_run(session, trace_id, exclude_eval_run_id=eval_run_id)
    previous_output = _snapshot_output_from_eval_run(prior) if prior else None
    current_output = (row.completion or "").strip() or "(empty)"

    if not previous_output:
        # Nothing to compare yet: run groundedness once to get a score + snapshot_output on this run so the
        # *next* regression can compare before/after. Avoids RQ "ok" jobs that only skip in under ~30ms.
        out, gd = run_groundedness_span_eval(
            session, trace_id, span_id, openai_api_key=openai_api_key
        )
        if out != "ok" or not gd:
            return out, gd
        if isinstance(gd, dict) and gd.get("kind") == "completed":
            merged = dict(gd)
            merged["regression_baseline_only"] = True
            return "ok", merged
        return out, gd

    ctx_text = extract_context_for_eval(row)
    context_block = (
        ctx_text
        if ctx_text
        else "(No retrieval context was recorded for this span.)"
    )
    user_query = (row.prompt or "").strip() or "(no user message captured)"

    if not (openai_api_key or "").strip() and not os.environ.get("OPENAI_API_KEY"):
        return "ok", {"kind": "skipped", "reason": "No OpenAI API key configured (env or BYOK)."}

    prev_prev = previous_output[:_PREVIEW]
    cur_prev = current_output[:_PREVIEW]
    ctx_prev = context_block[:_PREVIEW]
    q_prev = user_query[:_PREVIEW]

    try:
        judge = call_regression_compare_judge(
            user_query=q_prev,
            context=ctx_prev,
            previous_output=prev_prev,
            current_output=cur_prev,
            api_key=(openai_api_key.strip() if openai_api_key else None),
        )
    except RegressionCompareParseError as e:
        logger.warning(
            "regression compare parse failure trace_id=%s span_id=%s: %s",
            trace_id,
            span_id,
            e,
        )
        return "ok", {"kind": "error", "reason": str(e)[:2000]}
    except Exception as e:
        if is_transient_openai_error(e):
            logger.warning(
                "regression compare transient error trace_id=%s span_id=%s (job will retry): %s",
                trace_id,
                span_id,
                e,
            )
            raise
        logger.exception("regression compare failed trace_id=%s span_id=%s", trace_id, span_id)
        return "ok", {
            "kind": "error",
            "reason": str(e)[:2000],
            "traceback": traceback.format_exc()[-4000:],
        }

    previous_groundedness = _prior_groundedness_score(prior) if prior else None

    out_g, gd = run_groundedness_span_eval(
        session, trace_id, span_id, openai_api_key=openai_api_key
    )
    current_score: float | None = None
    gd_cost = 0.0
    gd_lat = 0
    if out_g == "ok" and gd and gd.get("kind") == "completed":
        if gd.get("score") is not None:
            current_score = float(gd["score"])
        gd_cost = float(gd.get("cost_usd") or 0)
        gd_lat = int(gd.get("latency_ms") or 0)

    delta_score: float | None = None
    if previous_groundedness is not None and current_score is not None:
        delta_score = current_score - previous_groundedness

    compare_cost = float(judge.cost_usd or 0)
    compare_lat = int(judge.latency_ms or 0)
    total_cost = compare_cost + gd_cost
    total_lat = compare_lat + gd_lat

    verdict = judge.output.verdict
    compare_score = float(judge.output.score)

    return "ok", {
        "kind": "completed",
        # Primary eval_run.score: regression compare judge (-1 .. 1) for sorting / avg regression signal
        "score": compare_score,
        "label": verdict,
        "reason": judge.output.reasoning,
        "cost_usd": total_cost,
        "latency_ms": total_lat,
        "previous_eval_run_id": prior.id if prior else None,
        "previous_score": previous_groundedness,
        "current_score": current_score,
        "delta_score": delta_score,
        "regression_compare_score": compare_score,
        "verdict": verdict,
        "snapshot_input": (row.prompt or "")[:50_000],
        "snapshot_output": (row.completion or "")[:50_000],
    }
