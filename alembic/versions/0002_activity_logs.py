"""activity logs

Revision ID: 0002_activity_logs
Revises: 0001_initial
Create Date: 2026-04-28 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_activity_logs"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("active_calories", sa.Float(), nullable=False),
        sa.Column("total_calories", sa.Float(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("sleep_minutes", sa.Float(), nullable=False),
        sa.Column("avg_heart_rate", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", "source", name="uq_activity_user_date_source"),
    )
    op.create_index(op.f("ix_activity_logs_date"), "activity_logs", ["date"], unique=False)
    op.create_index(op.f("ix_activity_logs_user_id"), "activity_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_logs_user_id"), table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_date"), table_name="activity_logs")
    op.drop_table("activity_logs")
