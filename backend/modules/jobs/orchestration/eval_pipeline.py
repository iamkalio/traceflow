"""
Eval run lifecycle after worker has invoked domain engines.

Separates *orchestration* (transitions, context payload shape) from *execution* (LLM calls).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from db.repositories.evaluation_repository import (
    set_eval_run_completed,
    set_eval_run_failed,
    set_eval_run_skipped,
)
from modules.evaluation.domain.evaluator import evaluator_family, normalize_evaluator_type


def finalize_eval_run_from_engine_detail(
    session: Session,
    *,
    eval_run_id: int,
    evaluator_type_raw: str | None,
    outcome: str,
    detail: dict[str, Any] | None,
) -> None:
    """
    Map engine ``detail`` dict (``kind`` = completed | skipped | error) onto eval_run row state.

    ``outcome`` is the string from span eval engines (e.g. ``not_found``); handled before this.
    """
    if outcome == "not_found":
        set_eval_run_failed(session, eval_run_id, error="Span not found for trace")
        return
    if not detail:
        set_eval_run_failed(session, eval_run_id, error="Eval produced no detail")
        return

    etype = normalize_evaluator_type(evaluator_type_raw)
    family = evaluator_family(etype or "")
    is_regression = family == "regression_compare"

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
        set_eval_run_skipped(session, eval_run_id, reasoning=str(detail.get("reason") or "skipped"))
    elif kind == "error":
        set_eval_run_failed(session, eval_run_id, error=str(detail.get("reason") or "error"))
    else:
        set_eval_run_failed(session, eval_run_id, error=f"Unexpected eval detail kind: {kind!r}")
