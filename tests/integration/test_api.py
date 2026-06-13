"""Integration tests — FastAPI endpoints via httpx AsyncClient + real DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


def _make_batch(n: int = 10, inject_anomaly: bool = False) -> dict:
    base_time = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    points = [
        {
            "metric_name": "cpu_usage",
            "value": 50.0 + i * 0.1,
            "timestamp": (base_time + timedelta(seconds=i * 30)).isoformat(),
            "source": "server-01",
        }
        for i in range(n)
    ]
    if inject_anomaly:
        points.append({
            "metric_name": "cpu_usage",
            "value": 99999.0,
            "timestamp": (base_time + timedelta(seconds=n * 30)).isoformat(),
            "source": "server-01",
        })
    return {"points": points}


# ── Health ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient):
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# ── Telemetry ingestion ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_clean_batch(client: AsyncClient):
    r = await client.post("/api/v1/telemetry", json=_make_batch(20))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "completed"
    assert d["points_processed"] == 20
    assert d["quality_report"]["quality_flag"] == "pass"


@pytest.mark.asyncio
async def test_ingest_detects_anomaly(client: AsyncClient):
    r = await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))
    assert r.status_code == 200
    d = r.json()
    assert d["anomalies_detected"] > 0
    assert 99999.0 in [a["value"] for a in d["anomalies"]]


@pytest.mark.asyncio
async def test_ingest_returns_processing_time(client: AsyncClient):
    r = await client.post("/api/v1/telemetry", json=_make_batch(5))
    assert r.json()["processing_time_ms"] > 0


@pytest.mark.asyncio
async def test_empty_batch_rejected(client: AsyncClient):
    r = await client.post("/api/v1/telemetry", json={"points": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invalid_metric_name_rejected(client: AsyncClient):
    batch = {"points": [{"metric_name": "bad name!@#", "value": 1.0, "source": "s"}]}
    assert (await client.post("/api/v1/telemetry", json=batch)).status_code == 422


@pytest.mark.asyncio
async def test_too_many_tags_rejected(client: AsyncClient):
    batch = {"points": [{
        "metric_name": "cpu", "value": 1.0, "source": "s",
        "tags": {f"key{i}": "v" for i in range(25)},
    }]}
    assert (await client.post("/api/v1/telemetry", json=batch)).status_code == 422


@pytest.mark.asyncio
async def test_extra_fields_in_batch_rejected(client: AsyncClient):
    batch = {**_make_batch(5), "malicious_field": "injected"}
    assert (await client.post("/api/v1/telemetry", json=batch)).status_code == 422


@pytest.mark.asyncio
async def test_no_sensitive_response_headers(client: AsyncClient):
    r = await client.get("/health")
    assert "x-api-key" not in r.headers
    assert "authorization" not in r.headers


# ── Persistence queries ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anomalies_persisted_and_queryable(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))
    r = await client.get("/api/v1/anomalies")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] >= 1
    assert any(item["value"] == 99999.0 for item in d["items"])


@pytest.mark.asyncio
async def test_anomalies_filter_by_severity(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))
    r = await client.get("/api/v1/anomalies", params={"severity": "critical"})
    assert r.status_code == 200
    assert all(item["severity"] == "critical" for item in r.json()["items"])


@pytest.mark.asyncio
async def test_anomalies_pagination(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))
    r = await client.get("/api/v1/anomalies", params={"limit": 1, "offset": 0})
    assert len(r.json()["items"]) <= 1


@pytest.mark.asyncio
async def test_reports_persisted_and_queryable(client: AsyncClient):
    submit = await client.post("/api/v1/telemetry", json=_make_batch(20))
    batch_id = submit.json()["batch_id"]
    r = await client.get("/api/v1/reports")
    assert r.status_code == 200
    assert any(item["batch_id"] == batch_id for item in r.json()["items"])


@pytest.mark.asyncio
async def test_reports_filter_by_flag(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(20))
    r = await client.get("/api/v1/reports", params={"flag": "pass"})
    assert all(item["quality_flag"] == "pass" for item in r.json()["items"])


@pytest.mark.asyncio
async def test_reports_summary(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))
    r = await client.get("/api/v1/reports/summary")
    assert r.status_code == 200
    d = r.json()
    assert d["total_batches"] >= 1
    assert d["total_anomalies"] >= 1
    assert isinstance(d["flag_counts"], dict)
    assert isinstance(d["severity_counts"], dict)


# ── Auth enforcement ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_telemetry_open_when_no_api_keys_configured(client: AsyncClient):
    """Default test config: API_KEYS=[] so no auth header needed."""
    assert (await client.post("/api/v1/telemetry", json=_make_batch(5))).status_code == 200


@pytest.mark.asyncio
async def test_telemetry_rejects_missing_key_when_configured(
    client: AsyncClient, monkeypatch
):
    from app.core import security
    monkeypatch.setattr(security.settings, "API_KEYS", ["test-key-123"])
    assert (await client.post("/api/v1/telemetry", json=_make_batch(5))).status_code == 401


@pytest.mark.asyncio
async def test_telemetry_accepts_valid_key_when_configured(
    client: AsyncClient, monkeypatch
):
    from app.core import security
    monkeypatch.setattr(security.settings, "API_KEYS", ["test-key-123"])
    r = await client.post(
        "/api/v1/telemetry",
        json=_make_batch(5),
        headers={"X-API-Key": "test-key-123"},
    )
    assert r.status_code == 200
