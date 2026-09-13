"""add user profile settings

Revision ID: 0004_user_profile_settings
Revises: 0003_user_target_weight
Create Date: 2026-05-12 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_user_profile_settings"
down_revision: str | None = "0003_user_target_weight"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("age_years", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("sex", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("activity_level", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "activity_level")
    op.drop_column("users", "sex")
    op.drop_column("users", "age_years")
