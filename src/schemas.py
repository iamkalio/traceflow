from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
