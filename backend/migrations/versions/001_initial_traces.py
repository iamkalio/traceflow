"""initial traces table for OTLP LLM events

Revision ID: 001_initial
Revises:
Create Date: 2025-03-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("span_id", sa.String(length=64), nullable=False),
        sa.Column("parent_span_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=32), server_default="llm", nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=512), server_default="", nullable=False),
        sa.Column("name", sa.String(length=1024), server_default="", nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("completion", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=64), server_default="success", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("trace_id", "span_id", name="uq_traces_trace_span"),
    )
    op.create_index("ix_traces_trace_id", "traces", ["trace_id"], unique=False)
    op.create_index("ix_traces_tenant_id", "traces", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_traces_tenant_id", table_name="traces")
    op.drop_index("ix_traces_trace_id", table_name="traces")
    op.drop_table("traces")
