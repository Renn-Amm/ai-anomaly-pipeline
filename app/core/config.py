"""
Application configuration — reads from environment variables.
Never hardcode secrets; use .env locally and GitHub Secrets in CI/CD.
"""

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Anomaly Detection Pipeline"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Security ───────────────────────────────────────────────────────────────
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    SECRET_KEY: str = "change-me-in-production-use-256-bit-random"  # noqa: S105
    API_KEYS: list[str] = []  # empty = auth disabled (dev only)
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Pipeline ───────────────────────────────────────────────────────────────
    ANOMALY_ZSCORE_THRESHOLD: float = 3.0
    ANOMALY_IQR_MULTIPLIER: float = 1.5
    PIPELINE_BATCH_SIZE: int = 1000
    PIPELINE_MAX_WORKERS: int = 4

    # ── Data Quality ───────────────────────────────────────────────────────────
    MAX_NULL_RATIO: float = 0.05
    MAX_DUPLICATE_RATIO: float = 0.02
    VALUE_RANGE_MIN: float = -1_000_000.0
    VALUE_RANGE_MAX: float = 1_000_000.0

    # ── Storage ────────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./pipeline.db"

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def use_memory_db_in_tests(cls, v: str) -> str:
        import os
        if os.environ.get("ENVIRONMENT") == "test":
            return "sqlite+aiosqlite:///:memory:"
        return v

    @field_validator("ANOMALY_ZSCORE_THRESHOLD")
    @classmethod
    def validate_zscore(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("ANOMALY_ZSCORE_THRESHOLD must be positive")
        return v

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Fail fast at startup if production is misconfigured."""
        if self.ENVIRONMENT == "production":
            placeholder = "change-me-in-production-use-256-bit-random"
            if self.SECRET_KEY == placeholder:
                raise ValueError(
                    "SECRET_KEY must be changed in production. "
                    'Run: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            if not self.API_KEYS:
                raise ValueError(
                    "API_KEYS must be set in production — "
                    "otherwise the API accepts unauthenticated writes."
                )
            if "*" in self.ALLOWED_HOSTS or "*" in self.ALLOWED_ORIGINS:
                raise ValueError(
                    "ALLOWED_HOSTS / ALLOWED_ORIGINS cannot be '*' in production."
                )
        return self

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
