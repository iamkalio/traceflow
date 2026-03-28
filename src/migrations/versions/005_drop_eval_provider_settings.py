"""drop eval_provider_settings (BYOK keys live in browser only)

Revision ID: 005_drop_eval_provider_settings
Revises: 004_add_eval_runs_and_provider_settings
Create Date: 2026-03-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_drop_eval_provider_settings"
down_revision: Union[str, None] = "004_add_eval_runs_and_provider_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("eval_provider_settings")


def downgrade() -> None:
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
