"""Persist normalized OTLP LLM events to PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Trace
from schemas import LLMEventNormalized


def parse_event_time(created_at: str) -> datetime:
    s = created_at
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)


def persist_normalized_events(session: Session, events: list[LLMEventNormalized]) -> None:
    """Insert events; duplicate (trace_id, span_id) pairs are ignored (idempotent)."""
    if not events:
        return
    for e in events:
        attrs = {
            "metadata": e.metadata,
            "resource": e.resource,
            "tenant_id": e.tenant_id,
        }
        stmt = (
            insert(Trace)
            .values(
                trace_id=e.trace_id,
                span_id=e.event_id,
                parent_span_id=e.parent_span_id,
                kind="llm",
                event_time=parse_event_time(e.created_at),
                model=e.model or "",
                name=e.span_name or "",
                prompt=e.input,
                completion=e.output,
                prompt_tokens=e.prompt_tokens,
                completion_tokens=e.completion_tokens,
                total_tokens=e.total_tokens,
                cost_usd=e.cost_usd,
                latency_ms=e.latency_ms,
                status=e.status or "success",
                error=e.error,
                attributes=attrs,
                tenant_id=e.tenant_id,
            )
            .on_conflict_do_nothing(constraint="uq_traces_trace_span")
        )
        session.execute(stmt)
    session.commit()
