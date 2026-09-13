"""add user target weight

Revision ID: 0003_user_target_weight
Revises: 0002_activity_logs
Create Date: 2026-04-29 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_user_target_weight"
down_revision: str | None = "0002_activity_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("target_weight_kg", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "target_weight_kg")
