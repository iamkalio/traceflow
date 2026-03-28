"""eval_run_groups + eval_runs.group_id for regression batches

Revision ID: 006_eval_run_groups
Revises: 005_drop_eval_provider_settings
Create Date: 2026-03-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_eval_run_groups"
down_revision: Union[str, None] = "005_drop_eval_provider_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_run_groups",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("total_jobs", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="running",
        ),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "eval_runs",
        sa.Column("group_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_eval_runs_group_id", "eval_runs", ["group_id"])
    op.create_foreign_key(
        "fk_eval_runs_group_id",
        "eval_runs",
        "eval_run_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_eval_runs_group_id", "eval_runs", type_="foreignkey")
    op.drop_index("ix_eval_runs_group_id", table_name="eval_runs")
    op.drop_column("eval_runs", "group_id")
    op.drop_table("eval_run_groups")
