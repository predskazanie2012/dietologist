from datetime import date, datetime, time

from sqlalchemy import JSON, BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    calorie_target: Mapped[float] = mapped_column(Float, default=1800)
    protein_target: Mapped[float] = mapped_column(Float, default=110)
    fat_target: Mapped[float] = mapped_column(Float, default=60)
    carb_target: Mapped[float] = mapped_column(Float, default=190)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    age_years: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(32))
    activity_level: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    standard_meals: Mapped[list["StandardMeal"]] = relationship(back_populates="user")
    meal_logs: Mapped[list["MealLog"]] = relationship(back_populates="user")
    reminder_settings: Mapped["ReminderSettings | None"] = relationship(back_populates="user")


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    calories_per_100g: Mapped[float] = mapped_column(Float, default=0)
    protein_per_100g: Mapped[float] = mapped_column(Float, default=0)
    fat_per_100g: Mapped[float] = mapped_column(Float, default=0)
    carbs_per_100g: Mapped[float] = mapped_column(Float, default=0)
    fiber_per_100g: Mapped[float] = mapped_column(Float, default=0)
    magnesium_per_100g: Mapped[float] = mapped_column(Float, default=0)
    potassium_per_100g: Mapped[float] = mapped_column(Float, default=0)
    calcium_per_100g: Mapped[float] = mapped_column(Float, default=0)
    iron_per_100g: Mapped[float] = mapped_column(Float, default=0)
    zinc_per_100g: Mapped[float] = mapped_column(Float, default=0)
    iodine_per_100g: Mapped[float] = mapped_column(Float, default=0)
    selenium_per_100g: Mapped[float] = mapped_column(Float, default=0)
    vitamin_c_per_100g: Mapped[float] = mapped_column(Float, default=0)
    vitamin_a_per_100g: Mapped[float] = mapped_column(Float, default=0)
    vitamin_e_per_100g: Mapped[float] = mapped_column(Float, default=0)
    omega3_per_100g: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StandardMeal(Base):
    __tablename__ = "standard_meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    total_calories: Mapped[float] = mapped_column(Float, default=0)
    total_protein: Mapped[float] = mapped_column(Float, default=0)
    total_fat: Mapped[float] = mapped_column(Float, default=0)
    total_carbs: Mapped[float] = mapped_column(Float, default=0)
    total_fiber: Mapped[float] = mapped_column(Float, default=0)
    micronutrients_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="standard_meals")
    items: Mapped[list["StandardMealItem"]] = relationship(back_populates="standard_meal")


class StandardMealItem(Base):
    __tablename__ = "standard_meal_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    standard_meal_id: Mapped[int] = mapped_column(ForeignKey("standard_meals.id", ondelete="CASCADE"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="RESTRICT"))
    grams: Mapped[float] = mapped_column(Float)

    standard_meal: Mapped[StandardMeal] = relationship(back_populates="items")
    food: Mapped[Food] = relationship()


class MealLog(Base):
    __tablename__ = "meal_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    meal_type: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(64))
    standard_meal_id: Mapped[int | None] = mapped_column(ForeignKey("standard_meals.id", ondelete="SET NULL"))
    raw_user_input: Mapped[str | None] = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    calories: Mapped[float] = mapped_column(Float, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0)
    fat: Mapped[float] = mapped_column(Float, default=0)
    carbs: Mapped[float] = mapped_column(Float, default=0)
    fiber: Mapped[float] = mapped_column(Float, default=0)
    micronutrients_json: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="meal_logs")
    standard_meal: Mapped[StandardMeal | None] = relationship()


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (UniqueConstraint("user_id", "date", "source", name="uq_activity_user_date_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    active_calories: Mapped[float] = mapped_column(Float, default=0)
    total_calories: Mapped[float] = mapped_column(Float, default=0)
    distance_m: Mapped[float] = mapped_column(Float, default=0)
    sleep_minutes: Mapped[float] = mapped_column(Float, default=0)
    avg_heart_rate: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64), default="health_connect")
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReminderSettings(Base):
    __tablename__ = "reminder_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    breakfast_time: Mapped[time] = mapped_column(Time, default=time(7, 0))
    lunch_time: Mapped[time] = mapped_column(Time, default=time(11, 0))
    dinner_time: Mapped[time] = mapped_column(Time, default=time(17, 0))
    evening_report_time: Mapped[time] = mapped_column(Time, default=time(17, 0))
    enabled: Mapped[bool] = mapped_column(default=True)

    user: Mapped[User] = relationship(back_populates="reminder_settings")
