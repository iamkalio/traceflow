"""add eval_results table

Revision ID: 003_add_eval_results
Revises: 002_add_trace_context
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_add_eval_results"
down_revision: Union[str, None] = "002_add_trace_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_results",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("span_id", sa.String(length=64), nullable=False),
        sa.Column("eval_name", sa.String(length=128), nullable=False),
        sa.Column("eval_version", sa.String(length=64), server_default="v1", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("label", sa.String(length=64), server_default="", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "trace_id",
            "span_id",
            "eval_name",
            "eval_version",
            name="uq_eval_results_span_eval",
        ),
    )
    op.create_index("ix_eval_results_trace_id", "eval_results", ["trace_id"], unique=False)
    op.create_index("ix_eval_results_span_id", "eval_results", ["span_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_eval_results_span_id", table_name="eval_results")
    op.drop_index("ix_eval_results_trace_id", table_name="eval_results")
    op.drop_table("eval_results")

