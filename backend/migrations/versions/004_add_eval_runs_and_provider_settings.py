"""add eval_runs + eval_provider_settings

Revision ID: 004_add_eval_runs_and_provider_settings
Revises: 003_add_eval_results
Create Date: 2026-03-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_add_eval_runs_and_provider_settings"
down_revision: Union[str, None] = "003_add_eval_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_provider_settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="openai"),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("span_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=True, index=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evaluator_type", sa.String(length=128), nullable=False),
        sa.Column("evaluator_version", sa.String(length=64), server_default="v1", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("eval_provider_settings")

