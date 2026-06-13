"""
Pydantic v2 models — strict typing, no extra fields allowed.
All inputs are validated and sanitised before processing.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Enums ──────────────────────────────────────────────────────────────────────

class AnomalyType(StrEnum):
    ZSCORE = "zscore"
    IQR = "iqr"
    NULL_SPIKE = "null_spike"
    DUPLICATE = "duplicate"
    OUT_OF_RANGE = "out_of_range"
    TIMESTAMP_GAP = "timestamp_gap"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QualityFlag(StrEnum):
    PASS = "pass"  # noqa: S105 — not a password
    WARN = "warn"
    FAIL = "fail"


# ── Input models ───────────────────────────────────────────────────────────────

_SAFE_METRIC_NAME = re.compile(r"^[a-zA-Z0-9_.\-]{1,128}$")


class TelemetryPoint(BaseModel):
    """Single telemetry reading from a sensor / service."""

    model_config = {"extra": "forbid"}

    metric_name: str = Field(..., description="Metric identifier")
    value: float = Field(..., description="Numeric reading")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    source: str = Field(..., min_length=1, max_length=64)
    tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("metric_name")
    @classmethod
    def validate_metric_name(cls, v: str) -> str:
        if not _SAFE_METRIC_NAME.match(v):
            raise ValueError(
                "metric_name must be 1–128 chars: letters, digits, _, ., -"
            )
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 tags per point")
        for k, val in v.items():
            if len(k) > 64 or len(val) > 256:
                raise ValueError("Tag keys ≤64 chars, values ≤256 chars")
        return v


class TelemetryBatch(BaseModel):
    """Batch of telemetry readings submitted for processing."""

    model_config = {"extra": "forbid"}

    batch_id: UUID = Field(default_factory=uuid4)
    points: list[TelemetryPoint] = Field(..., min_length=1, max_length=10_000)
    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )

    @model_validator(mode="after")
    def check_batch_not_empty(self) -> TelemetryBatch:
        if not self.points:
            raise ValueError("Batch must contain at least one point")
        return self


# ── Output models ──────────────────────────────────────────────────────────────

class AnomalyRecord(BaseModel):
    """Detected anomaly with full audit trail."""

    anomaly_id: UUID = Field(default_factory=uuid4)
    batch_id: UUID
    metric_name: str
    value: float
    timestamp: datetime
    anomaly_type: AnomalyType
    severity: Severity
    score: float | None = Field(None, description="Statistical score")
    description: str
    resolution_hint: str


class DataQualityReport(BaseModel):
    """Summary quality assessment for a processed batch."""

    batch_id: UUID
    total_points: int
    null_count: int
    duplicate_count: int
    out_of_range_count: int
    null_ratio: float
    duplicate_ratio: float
    quality_flag: QualityFlag
    issues: list[str] = Field(default_factory=list)
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )


class PipelineResult(BaseModel):
    """Full pipeline output for a submitted batch."""

    batch_id: UUID
    status: str
    points_processed: int
    anomalies_detected: int
    anomalies: list[AnomalyRecord]
    quality_report: DataQualityReport
    processing_time_ms: float
    pipeline_version: str = "1.0.0"
