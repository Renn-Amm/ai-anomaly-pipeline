"""
Application configuration — reads from environment variables.
Never hardcode secrets; use .env locally and GitHub Secrets in CI/CD.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Anomaly Detection Pipeline"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Security ───────────────────────────────────────────────────────────────
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    SECRET_KEY: str = "change-me-in-production-use-256-bit-random"

    # ── Pipeline ───────────────────────────────────────────────────────────────
    ANOMALY_ZSCORE_THRESHOLD: float = 3.0
    ANOMALY_IQR_MULTIPLIER: float = 1.5
    PIPELINE_BATCH_SIZE: int = 1000
    PIPELINE_MAX_WORKERS: int = 4

    # ── Data Quality ───────────────────────────────────────────────────────────
    MAX_NULL_RATIO: float = 0.05        # Flag if >5 % nulls
    MAX_DUPLICATE_RATIO: float = 0.02   # Flag if >2 % duplicates
    VALUE_RANGE_MIN: float = -1_000_000.0
    VALUE_RANGE_MAX: float = 1_000_000.0

    # ── Storage (optional — only needed when wired to real storage) ────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./pipeline.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def use_memory_db_in_tests(cls, v, info):
        # Pytest sets ENVIRONMENT=test via env var before Settings is built;
        # field order means ENVIRONMENT may not be validated yet, so check raw env.
        import os
        if os.environ.get("ENVIRONMENT") == "test":
            return "sqlite+aiosqlite:///:memory:"
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v

    @field_validator("ANOMALY_ZSCORE_THRESHOLD")
    @classmethod
    def validate_zscore(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("ANOMALY_ZSCORE_THRESHOLD must be positive")
        return v

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
