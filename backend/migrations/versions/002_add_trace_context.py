"""add context column to traces

Revision ID: 002_add_trace_context
Revises: 001_initial
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_add_trace_context"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("traces", sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_traces_context", "traces", ["context"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_traces_context", table_name="traces")
    op.drop_column("traces", "context")

