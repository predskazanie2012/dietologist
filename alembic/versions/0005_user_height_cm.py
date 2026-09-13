"""add user height

Revision ID: 0005_user_height_cm
Revises: 0004_user_profile_settings
Create Date: 2026-05-31 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_user_height_cm"
down_revision: str | None = "0004_user_profile_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("height_cm", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "height_cm")
