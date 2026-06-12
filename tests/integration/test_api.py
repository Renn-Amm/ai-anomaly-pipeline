"""
Integration tests — FastAPI endpoints via httpx AsyncClient.
Tests run against the real application (no mocking of business logic).
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with LifespanManager(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ── Health Endpoints ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


# ── Telemetry Ingestion ────────────────────────────────────────────────────────

def _make_batch(n: int = 10, inject_anomaly: bool = False) -> dict:
    """Build a valid batch payload."""
    base_time = datetime(2024, 6, 1, 10, 0, 0)
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


@pytest.mark.asyncio
async def test_ingest_clean_batch(client: AsyncClient):
    response = await client.post("/api/v1/telemetry", json=_make_batch(20))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["points_processed"] == 20
    assert "quality_report" in data
    assert "anomalies" in data
    assert data["quality_report"]["quality_flag"] == "pass"


@pytest.mark.asyncio
async def test_ingest_detects_anomaly(client: AsyncClient):
    response = await client.post(
        "/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["anomalies_detected"] > 0
    anomaly_values = [a["value"] for a in data["anomalies"]]
    assert 99999.0 in anomaly_values


@pytest.mark.asyncio
async def test_ingest_returns_processing_time(client: AsyncClient):
    response = await client.post("/api/v1/telemetry", json=_make_batch(5))
    assert response.status_code == 200
    assert response.json()["processing_time_ms"] > 0


@pytest.mark.asyncio
async def test_ingest_empty_batch_rejected(client: AsyncClient):
    response = await client.post("/api/v1/telemetry", json={"points": []})
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_ingest_invalid_metric_name_rejected(client: AsyncClient):
    batch = {
        "points": [{
            "metric_name": "invalid metric name!@#",
            "value": 1.0,
            "timestamp": datetime(2024, 1, 1).isoformat(),
            "source": "s",
        }]
    }
    response = await client.post("/api/v1/telemetry", json=batch)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_too_many_tags_rejected(client: AsyncClient):
    batch = {
        "points": [{
            "metric_name": "cpu",
            "value": 1.0,
            "timestamp": datetime(2024, 1, 1).isoformat(),
            "source": "s",
            "tags": {f"key{i}": "v" for i in range(25)},  # exceeds max 20
        }]
    }
    response = await client.post("/api/v1/telemetry", json=batch)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_response_has_no_sensitive_headers(client: AsyncClient):
    response = await client.get("/health")
    assert "server" not in response.headers or response.headers.get("server", "") == ""
    # X-Process-Time-Ms is fine — it's not sensitive
    assert "x-api-key" not in response.headers
    assert "authorization" not in response.headers


# ── Security: Unexpected Fields Stripped ──────────────────────────────────────

@pytest.mark.asyncio
async def test_extra_fields_in_batch_rejected(client: AsyncClient):
    batch = _make_batch(5)
    batch["malicious_field"] = "injected"
    # Pydantic forbids extra fields on TelemetryBatch
    response = await client.post("/api/v1/telemetry", json=batch)
    assert response.status_code == 422


# ── Persistence: Anomalies & Reports ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_anomalies_persisted_and_queryable(client: AsyncClient):
    submit = await client.post(
        "/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True)
    )
    assert submit.status_code == 200

    response = await client.get("/api/v1/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(item["value"] == 99999.0 for item in data["items"])


@pytest.mark.asyncio
async def test_anomalies_filter_by_severity(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))

    response = await client.get("/api/v1/anomalies", params={"severity": "critical"})
    assert response.status_code == 200
    data = response.json()
    assert all(item["severity"] == "critical" for item in data["items"])


@pytest.mark.asyncio
async def test_anomalies_pagination(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))

    response = await client.get("/api/v1/anomalies", params={"limit": 1, "offset": 0})
    assert response.status_code == 200
    assert len(response.json()["items"]) <= 1


@pytest.mark.asyncio
async def test_reports_persisted_and_queryable(client: AsyncClient):
    submit = await client.post("/api/v1/telemetry", json=_make_batch(20))
    batch_id = submit.json()["batch_id"]

    response = await client.get("/api/v1/reports")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(item["batch_id"] == batch_id for item in data["items"])


@pytest.mark.asyncio
async def test_reports_filter_by_flag(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(20))

    response = await client.get("/api/v1/reports", params={"flag": "pass"})
    assert response.status_code == 200
    data = response.json()
    assert all(item["quality_flag"] == "pass" for item in data["items"])


@pytest.mark.asyncio
async def test_reports_summary(client: AsyncClient):
    await client.post("/api/v1/telemetry", json=_make_batch(30, inject_anomaly=True))

    response = await client.get("/api/v1/reports/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_batches"] >= 1
    assert data["total_anomalies"] >= 1
    assert isinstance(data["flag_counts"], dict)
    assert isinstance(data["severity_counts"], dict)
