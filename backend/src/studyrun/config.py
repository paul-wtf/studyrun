from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice(BaseModel):
    input: float
    output: float
    cache_read: float
    cache_write: float


# USD per million tokens. Batch requests cost half of every price.
PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-sonnet-5-5": ModelPrice(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STUDYRUN_",
        case_sensitive=False,
        populate_by_name=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://studyrun:studyrun@localhost:5432/studyrun"
    log_level: str = "INFO"
    timezone: str = "Europe/Berlin"
    worker_enabled: bool = True

    anthropic_api_key: str = ""
    model_generate: str = "claude-opus-5-5"
    model_verify: str = "claude-sonnet-5-5"
    model_grade: str = "claude-opus-5-5"

    daily_ai_cap_usd: float = Field(default=0.50, ge=0)
    generation_daily_budget_usd: float = Field(default=10.00, ge=0)
    generation_confirm_usd: float = Field(default=5.00, ge=0)
    generation_estimate_usd_per_page: float = Field(default=0.025, ge=0)
    generation_max_in_flight: int = Field(default=3, ge=1)

    run_review_cap: int = Field(default=8, ge=0)
    run_new_items: int = Field(default=4, ge=0)

    max_chapter_pages: int = Field(default=40, ge=1)
    chapter_window_pages: int = Field(default=15, ge=1)

    upload_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
