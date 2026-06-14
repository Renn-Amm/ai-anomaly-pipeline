"""Unit tests — production security config validation."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestProductionValidation:
    def test_dev_environment_allows_defaults(self):
        s = Settings(ENVIRONMENT="development")
        assert s.SECRET_KEY  # default is fine in dev

    def test_production_rejects_default_secret_key(self):
        # Must pass the default placeholder explicitly to trigger the validator
        with pytest.raises(ValidationError):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="change-me-in-production-use-256-bit-random",
                API_KEYS=["a-real-key"],
                ALLOWED_HOSTS=["api.example.com"],
                ALLOWED_ORIGINS=["https://example.com"],
            )

    def test_production_rejects_empty_api_keys(self):
        with pytest.raises(ValidationError):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="a-real-256-bit-secret-xxxxxxxxxxxxxxxx",
                API_KEYS=[],
                ALLOWED_HOSTS=["api.example.com"],
                ALLOWED_ORIGINS=["https://example.com"],
            )

    def test_production_rejects_wildcard_hosts(self):
        with pytest.raises(ValidationError):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="a-real-256-bit-secret-xxxxxxxxxxxxxxxx",
                API_KEYS=["a-real-key"],
                ALLOWED_HOSTS=["*"],
                ALLOWED_ORIGINS=["https://example.com"],
            )

    def test_production_passes_with_correct_config(self):
        s = Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-real-256-bit-secret-xxxxxxxxxxxxxxxx",
            API_KEYS=["a-real-key"],
            ALLOWED_HOSTS=["api.example.com"],
            ALLOWED_ORIGINS=["https://example.com"],
        )
        assert s.ENVIRONMENT == "production"
