"""
Authentication — simple API key check for write endpoints.

For production, set API_KEYS to a comma-separated list of long random
strings (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
and require clients to send: `X-API-Key: <key>`

Read-only endpoints (anomalies/reports) are left open by default since they
serve dashboards; flip READ_REQUIRES_AUTH=true in .env to lock those down too.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

settings = get_settings()


def _constant_time_in(candidate: str, valid_keys: list[str]) -> bool:
    """Compare against every key in constant time to avoid timing attacks."""
    found = False
    for key in valid_keys:
        if hmac.compare_digest(candidate, key):
            found = True
    return found


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    FastAPI dependency — raises 401 if API_KEYS is configured and the
    request doesn't present a valid X-API-Key header.

    If API_KEYS is empty (local/dev default), auth is skipped entirely —
    but production deployments MUST set API_KEYS or this dependency will
    reject all requests once ENVIRONMENT=production (see config validator).
    """
    if not settings.API_KEYS:
        return  # auth disabled — dev/test mode

    if x_api_key is None or not _constant_time_in(x_api_key, settings.API_KEYS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. Send it as 'X-API-Key' header.",
        )