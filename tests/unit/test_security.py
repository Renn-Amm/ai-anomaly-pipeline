"""Unit tests — API key authentication dependency."""

import pytest
from fastapi import HTTPException

from app.core import security


class TestApiKeyAuth:
    def test_auth_skipped_when_no_keys_configured(self, monkeypatch):
        monkeypatch.setattr(security.settings, "API_KEYS", [])
        # Should not raise even with no header
        import asyncio

        asyncio.run(security.require_api_key(x_api_key=None))

    def test_valid_key_accepted(self, monkeypatch):
        monkeypatch.setattr(security.settings, "API_KEYS", ["secret123"])
        import asyncio

        asyncio.run(security.require_api_key(x_api_key="secret123"))

    def test_missing_key_rejected(self, monkeypatch):
        monkeypatch.setattr(security.settings, "API_KEYS", ["secret123"])
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(security.require_api_key(x_api_key=None))
        assert exc_info.value.status_code == 401

    def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setattr(security.settings, "API_KEYS", ["secret123"])
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(security.require_api_key(x_api_key="wrong"))
        assert exc_info.value.status_code == 401

    def test_constant_time_compare_multiple_keys(self):
        keys = ["key1", "key2", "key3"]
        assert security._constant_time_in("key2", keys) is True
        assert security._constant_time_in("nope", keys) is False
