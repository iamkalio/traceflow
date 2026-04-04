from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
    One normalized LLM event from an OTLP span (traceflow.type == llm_call).

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
