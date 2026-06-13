"""Unit tests — production security config validation."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestProductionValidation:
    def test_dev_environment_allows_defaults(self):
        s = Settings(ENVIRONMENT="development")
        assert s.SECRET_KEY  # default is fine in dev

    def test_production_rejects_default_secret_key(self):
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings(
                ENVIRONMENT="production",
                API_KEYS=["a-real-key"],
                ALLOWED_HOSTS=["api.example.com"],
                ALLOWED_ORIGINS=["https://example.com"],
            )

    def test_production_rejects_empty_api_keys(self):
        with pytest.raises(ValidationError, match="API_KEYS"):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="a-real-256-bit-secret-xxxxxxxxxxxxxxxx",
                ALLOWED_HOSTS=["api.example.com"],
                ALLOWED_ORIGINS=["https://example.com"],
            )

    def test_production_rejects_wildcard_hosts(self):
        with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
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