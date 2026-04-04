from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvalResultOut(BaseModel):
    """One eval row for API responses (e.g. GET /v1/traces/{trace_id}/evals)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    span_id: str
    eval_name: str
    eval_version: str
    score: float | None
    label: str
    reason: str | None
    details: dict[str, Any]
    created_at: datetime


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int | None = None
    trace_id: str
    span_id: str | None
    status: str
    evaluator_type: str
    evaluator_version: str
    score: float | None = None
    label: str | None = None
    reasoning: str | None = None
    context: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class FailureTypeCountOut(BaseModel):
    failure_type: str
    count: int


class InsightsSummaryOut(BaseModel):
    """Aggregates over recent eval_runs (global insights)."""

    sample_size: int
    completed_with_score: int
    avg_score: float | None
    good_count: int
    borderline_count: int
    bad_count: int
    good_pct: float | None
    borderline_pct: float | None
    bad_pct: float | None
    total_eval_cost_usd: float
    top_failure_types: list[FailureTypeCountOut]


class WorstRegressionOut(BaseModel):
    """Lowest delta_score first (most negative groundedness drift)."""

    trace_id: str
    delta_score: float | None = None
    verdict: str = ""
    regression_compare_score: float | None = None


class EvalRunGroupDetailOut(BaseModel):
    """One regression / batch group plus rollups and child runs."""

    id: int
    name: str
    status: str
    total_jobs: int
    tenant_id: str | None
    created_at: datetime
    avg_score: float | None
    good_count: int
    borderline_count: int
    bad_count: int
    good_pct: float | None
    borderline_pct: float | None
    bad_pct: float | None
    total_eval_cost_usd: float
    completed_jobs: int
    top_failure_types: list[FailureTypeCountOut]
    eval_runs: list[EvalRunOut]
    pct_improved: float | None = None
    pct_regressed: float | None = None
    pct_unchanged: float | None = None
    avg_delta_score: float | None = None
    worst_regressions: list[WorstRegressionOut] = Field(default_factory=list)
    regression_summary: str = ""


class RegressionRunIn(BaseModel):
    n: int = Field(ge=1, le=500, description="Compare the N most recently active traces (vs prior eval snapshot).")
    eval_name: str = "regression_compare_v1"


class RegressionRunQueuedOut(BaseModel):
    status: str
    group_id: int
    eval_run_ids: list[int]
