from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Identity, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Trace(Base):
    """One row per OTLP span ingested as an LLM event (idempotent on trace_id + span_id)."""

    __tablename__ = "traces"
    __table_args__ = (UniqueConstraint("trace_id", "span_id", name="uq_traces_trace_span"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    span_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="llm")
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    name: Mapped[str] = mapped_column(String(1024), nullable=False, server_default="")
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default="success")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
