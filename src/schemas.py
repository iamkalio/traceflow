from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TraceIn(BaseModel):
    trace_id: str
    span_id: str | None = None
    parent_span_id: str | None = None
    kind: str = "llm"  # "llm" | "tool" | "rag" | "agent" etc.
    timestamp: datetime | None = None
    model: str = ""
    name: str = ""
    prompt: str = ""
    completion: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int | None = None
    status: str = "success"
    error: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class LLMEventNormalized(BaseModel):
    """
    One normalized LLM event from an OTLP span (traceflow.type == llm_call or legacy gen_ai).

    event_id: hex-encoded OpenTelemetry span_id bytes (typically 8 bytes → 16 hex chars).
    If span_id is empty, a random UUID string is used instead (documented choice).
    trace_id: hex-encoded trace_id (16 bytes → 32 hex chars per W3C trace context).
    """

    event_id: str
    trace_id: str
    parent_span_id: str | None = None
    span_name: str = ""
    model: str | None = None
    input: str | None = None
    output: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    status: str | None = None
    error: str | None = None
    created_at: str  # RFC3339 UTC
    resource: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None

    @field_validator("model", "input", "output", "error", "status", "span_name", mode="before")
    @classmethod
    def coerce_optional_str(cls, v: Any) -> str | None:
        if v is None:
            return None
        return str(v)

    @field_validator(
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        mode="before",
    )
    @classmethod
    def coerce_int(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str):
            try:
                return int(v.strip())
            except ValueError:
                return None
        return None

    @field_validator("cost_usd", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float | None:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError:
                return None
        return None


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


class TraceListItemOut(BaseModel):
    """One row per trace_id for list views."""

    trace_id: str
    name: str | None = None
    input: str | None = None
    output: str | None = None
    annotations: int | None = None  # legacy (eval_results count); will be replaced by eval_status
    eval_status: str | None = None  # pending | queued | running | completed | failed | skipped
    eval_score: float | None = None
    eval_label: str | None = None
    start_time: datetime | None = None
    latency_ms: int | None = None
    first_seen: datetime
    last_seen: datetime
    span_count: int
    status: str
    total_tokens: int | None
    total_cost_usd: float | None


class TraceListResponse(BaseModel):
    items: list[TraceListItemOut]
    next_cursor: str | None = None


class TraceSpanOut(BaseModel):
    """One span row for trace detail views."""

    model_config = ConfigDict(from_attributes=True)

    trace_id: str
    span_id: str
    parent_span_id: str | None
    kind: str
    event_time: datetime
    model: str
    name: str
    prompt: str | None
    completion: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    status: str
    error: str | None
    context: dict | None
    attributes: dict
    tenant_id: str | None
