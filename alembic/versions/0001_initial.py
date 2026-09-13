"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-27 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("calorie_target", sa.Float(), nullable=False),
        sa.Column("protein_target", sa.Float(), nullable=False),
        sa.Column("fat_target", sa.Float(), nullable=False),
        sa.Column("carb_target", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)

    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("calories_per_100g", sa.Float(), nullable=False),
        sa.Column("protein_per_100g", sa.Float(), nullable=False),
        sa.Column("fat_per_100g", sa.Float(), nullable=False),
        sa.Column("carbs_per_100g", sa.Float(), nullable=False),
        sa.Column("fiber_per_100g", sa.Float(), nullable=False),
        sa.Column("magnesium_per_100g", sa.Float(), nullable=False),
        sa.Column("potassium_per_100g", sa.Float(), nullable=False),
        sa.Column("calcium_per_100g", sa.Float(), nullable=False),
        sa.Column("iron_per_100g", sa.Float(), nullable=False),
        sa.Column("zinc_per_100g", sa.Float(), nullable=False),
        sa.Column("iodine_per_100g", sa.Float(), nullable=False),
        sa.Column("selenium_per_100g", sa.Float(), nullable=False),
        sa.Column("vitamin_c_per_100g", sa.Float(), nullable=False),
        sa.Column("vitamin_a_per_100g", sa.Float(), nullable=False),
        sa.Column("vitamin_e_per_100g", sa.Float(), nullable=False),
        sa.Column("omega3_per_100g", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_foods_name"), "foods", ["name"], unique=True)

    op.create_table(
        "standard_meals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total_calories", sa.Float(), nullable=False),
        sa.Column("total_protein", sa.Float(), nullable=False),
        sa.Column("total_fat", sa.Float(), nullable=False),
        sa.Column("total_carbs", sa.Float(), nullable=False),
        sa.Column("total_fiber", sa.Float(), nullable=False),
        sa.Column("micronutrients_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_standard_meals_name"), "standard_meals", ["name"], unique=False)
    op.create_index(op.f("ix_standard_meals_user_id"), "standard_meals", ["user_id"], unique=False)

    op.create_table(
        "standard_meal_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("standard_meal_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["standard_meal_id"], ["standard_meals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_standard_meal_items_standard_meal_id"), "standard_meal_items", ["standard_meal_id"], unique=False)

    op.create_table(
        "meal_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meal_type", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("standard_meal_id", sa.Integer(), nullable=True),
        sa.Column("raw_user_input", sa.Text(), nullable=True),
        sa.Column("photo_file_id", sa.String(length=255), nullable=True),
        sa.Column("calories", sa.Float(), nullable=False),
        sa.Column("protein", sa.Float(), nullable=False),
        sa.Column("fat", sa.Float(), nullable=False),
        sa.Column("carbs", sa.Float(), nullable=False),
        sa.Column("fiber", sa.Float(), nullable=False),
        sa.Column("micronutrients_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["standard_meal_id"], ["standard_meals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meal_logs_datetime"), "meal_logs", ["datetime"], unique=False)
    op.create_index(op.f("ix_meal_logs_user_id"), "meal_logs", ["user_id"], unique=False)

    op.create_table(
        "weight_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_weight_logs_date"), "weight_logs", ["date"], unique=False)
    op.create_index(op.f("ix_weight_logs_user_id"), "weight_logs", ["user_id"], unique=False)

    op.create_table(
        "reminder_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("breakfast_time", sa.Time(), nullable=False),
        sa.Column("lunch_time", sa.Time(), nullable=False),
        sa.Column("dinner_time", sa.Time(), nullable=False),
        sa.Column("evening_report_time", sa.Time(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reminder_settings_user_id"), "reminder_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_reminder_settings_user_id"), table_name="reminder_settings")
    op.drop_table("reminder_settings")
    op.drop_index(op.f("ix_weight_logs_user_id"), table_name="weight_logs")
    op.drop_index(op.f("ix_weight_logs_date"), table_name="weight_logs")
    op.drop_table("weight_logs")
    op.drop_index(op.f("ix_meal_logs_user_id"), table_name="meal_logs")
    op.drop_index(op.f("ix_meal_logs_datetime"), table_name="meal_logs")
    op.drop_table("meal_logs")
    op.drop_index(op.f("ix_standard_meal_items_standard_meal_id"), table_name="standard_meal_items")
    op.drop_table("standard_meal_items")
    op.drop_index(op.f("ix_standard_meals_user_id"), table_name="standard_meals")
    op.drop_index(op.f("ix_standard_meals_name"), table_name="standard_meals")
    op.drop_table("standard_meals")
    op.drop_index(op.f("ix_foods_name"), table_name="foods")
    op.drop_table("foods")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
