from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
