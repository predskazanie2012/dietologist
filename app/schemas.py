from datetime import date, datetime, time

from pydantic import BaseModel, Field


MICRONUTRIENT_KEYS = [
    "vitamin_a",
    "vitamin_c",
    "vitamin_d",
    "vitamin_e",
    "vitamin_k",
    "thiamin",
    "riboflavin",
    "niacin",
    "pantothenic_acid",
    "vitamin_b6",
    "biotin",
    "folate",
    "vitamin_b12",
    "choline",
    "calcium",
    "chloride",
    "chromium",
    "copper",
    "fluoride",
    "iodine",
    "iron",
    "magnesium",
    "manganese",
    "molybdenum",
    "phosphorus",
    "potassium",
    "selenium",
    "sodium",
    "zinc",
    "omega3",
]


class NutrientTotals(BaseModel):
    calories: float = 0
    protein: float = 0
    fat: float = 0
    carbs: float = 0
    fiber: float = 0
    micronutrients: dict[str, float] = Field(default_factory=dict)


class FoodRead(BaseModel):
    id: int
    name: str
    calories_per_100g: float
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float
    fiber_per_100g: float

    model_config = {"from_attributes": True}


class MealLogRead(BaseModel):
    id: int
    datetime: datetime
    meal_type: str | None
    source_type: str
    calories: float
    protein: float
    fat: float
    carbs: float
    fiber: float
    micronutrients_json: dict
    confidence: float | None
    notes: str | None

    model_config = {"from_attributes": True}


class ActivitySyncIn(BaseModel):
    telegram_id: int
    date: date
    steps: int = Field(default=0, ge=0)
    active_calories: float = Field(default=0, ge=0)
    total_calories: float = Field(default=0, ge=0)
    distance_m: float = Field(default=0, ge=0)
    sleep_minutes: float = Field(default=0, ge=0)
    avg_heart_rate: float | None = Field(default=None, ge=20, le=240)
    source: str = "health_connect"
    raw: dict = Field(default_factory=dict)


class ActivityLogRead(BaseModel):
    date: date
    steps: int
    active_calories: float
    total_calories: float
    distance_m: float
    sleep_minutes: float
    avg_heart_rate: float | None
    source: str

    model_config = {"from_attributes": True}


class ReminderSettingsRead(BaseModel):
    breakfast_time: time
    lunch_time: time
    dinner_time: time
    evening_report_time: time
    enabled: bool

    model_config = {"from_attributes": True}


class DailyReport(BaseModel):
    date: date
    calories_fact: float
    calories_target: float
    protein_fact: float
    protein_target: float
    fat_fact: float
    fat_target: float
    carbs_fact: float
    carbs_target: float
    fiber_fact: float
    meal_count: int = 0
    day_goal_met: bool = False
    streak_days: int = 0
    steps: int = 0
    active_calories: float = 0
    total_burned_calories: float = 0
    estimated_balance_calories: float | None = None
    sleep_minutes: float = 0
    avg_heart_rate: float | None = None
    status: str
    good: str
    improve: str


class WeeklyReport(BaseModel):
    period_label: str = "Неделя"
    period_days: int = 7
    start_date: date
    end_date: date
    calories_fact: float
    calories_target: float
    avg_calories: float
    avg_protein: float
    avg_fat: float
    avg_carbs: float
    protein_target: float
    fat_target: float
    carbs_target: float
    weight_delta_kg: float | None
    qualified_days: int = 0
    best_streak_days: int = 0
    diet_days: list[bool] = Field(default_factory=list)
    micronutrients_7d: dict[str, float]
    recommendations: list[str]
    score: int = 0
    motivation: str = ""
    glycemic_score: int = 0
    glycemic_comment: str = ""
    inflammation_score: int = 0
    inflammation_comment: str = ""
    acid_base_score: int = 0
    acid_base_comment: str = ""


class YearWeekSummary(BaseModel):
    start_date: date
    end_date: date
    score: int = 0
    has_entries: bool = False
    qualified_days: int = 0
    avg_calories: float = 0


class YearMonthSummary(BaseModel):
    month: int
    label: str
    start_date: date
    end_date: date
    week_summaries: list[YearWeekSummary] = Field(default_factory=list)
    score: int = 0
    has_entries: bool = False
    qualified_days: int = 0
    avg_calories: float = 0


class YearReport(BaseModel):
    year: int
    start_date: date
    end_date: date
    months: list[YearMonthSummary] = Field(default_factory=list)
    score: int = 0


class AllTimeYearSummary(BaseModel):
    year: int
    start_date: date
    end_date: date
    months: list[YearMonthSummary] = Field(default_factory=list)
    score: int = 0
    has_entries: bool = False
    qualified_days: int = 0
    total_entries: int = 0
    avg_calories: float = 0


class AllTimeReport(BaseModel):
    start_date: date
    end_date: date
    years: list[AllTimeYearSummary] = Field(default_factory=list)
    score: int = 0
    qualified_days: int = 0
    total_entries: int = 0
    avg_calories: float = 0
    weight_delta_kg: float | None = None
