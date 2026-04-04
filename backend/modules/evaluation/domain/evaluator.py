"""evaluator routing and classification (no DB, no HTTP)."""

from __future__ import annotations

from typing import Literal

EvaluatorFamily = Literal["groundedness", "regression_compare", "unknown"]


def normalize_evaluator_type(raw: str | None) -> str:
    return (raw or "").strip().lower()


def evaluator_family(etype: str) -> EvaluatorFamily:
    t = normalize_evaluator_type(etype)
    if t.startswith("groundedness"):
        return "groundedness"
    if t.startswith("regression_compare"):
        return "regression_compare"
    return "unknown"
