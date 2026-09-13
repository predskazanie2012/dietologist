from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    api_admin_token: str = ""

    database_url: str = "sqlite+aiosqlite:///./dietologist-demo.db"
    telegram_bot_token: str = ""
    telegram_admin_id: int | None = None
    telegram_allowed_ids: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    health_sync_token: str = ""

    default_timezone: str = "UTC"
    default_calorie_target: float = 1800
    default_protein_target: float = 110
    default_fat_target: float = 60
    default_carb_target: float = 190

    reminder_breakfast_time: str = Field(default="07:00")
    reminder_lunch_time: str = Field(default="11:00")
    reminder_dinner_time: str = Field(default="17:00")
    reminder_evening_report_time: str = Field(default="17:00")

    @field_validator("telegram_admin_id", mode="before")
    @classmethod
    def empty_admin_id_as_none(cls, value):
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
