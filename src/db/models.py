from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Identity, Integer, String, Text, UniqueConstraint, func, text
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
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvalResult(Base):
    """One row per eval run on a single span (trace_id + span_id)."""

    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("trace_id", "span_id", "eval_name", "eval_version", name="uq_eval_results_span_eval"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    span_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    eval_name: Mapped[str] = mapped_column(String(128), nullable=False)
    eval_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvalRunGroup(Base):
    """Batch / regression run: many eval_runs enqueued together (e.g. last N traces)."""

    __tablename__ = "eval_run_groups"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    total_jobs: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="running")
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("eval_run_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    span_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # pending | queued | running | completed | failed | skipped
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    evaluator_type: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
