"""Unit tests — data quality service."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import uuid4

from app.models.schemas import QualityFlag, TelemetryPoint
from app.services.data_quality import assess_data_quality


def make_point(value: float, metric: str = "m", source: str = "s") -> TelemetryPoint:
    return TelemetryPoint(
        metric_name=metric,
        value=value,
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        source=source,
    )


class TestDataQuality:
    def test_clean_batch_passes(self):
        points = [make_point(float(i), source=f"s{i}") for i in range(100)]
        report = assess_data_quality(points, uuid4())
        assert report.quality_flag == QualityFlag.PASS
        assert report.null_count == 0
        assert report.duplicate_count == 0

    def test_flags_high_null_ratio(self):
        points = [make_point(float(i), source=f"s{i}") for i in range(90)]
        for i in range(10):
            points.append(
                TelemetryPoint(
                    metric_name="m",
                    value=math.inf,
                    timestamp=datetime(2024, 1, 1, 12, 0, i + 1, tzinfo=UTC),
                    source=f"bad{i}",
                )
            )
        report = assess_data_quality(points, uuid4())
        assert report.null_count == 10
        assert report.null_ratio > 0.05
        assert report.quality_flag in (QualityFlag.WARN, QualityFlag.FAIL)

    def test_flags_duplicates(self):
        base = make_point(1.0)
        report = assess_data_quality([base] * 10, uuid4())
        assert report.duplicate_count == 9

    def test_out_of_range_counted(self):
        points = [make_point(1.0, source=f"s{i}") for i in range(10)]
        points.append(
            TelemetryPoint(
                metric_name="m",
                value=9_000_000.0,
                timestamp=datetime(2024, 1, 1, 12, 0, 1, tzinfo=UTC),
                source="oor",
            )
        )
        assert assess_data_quality(points, uuid4()).out_of_range_count == 1

    def test_batch_id_in_report(self):
        batch_id = uuid4()
        assert assess_data_quality([make_point(1.0, source="s1")], batch_id).batch_id == batch_id

    def test_empty_issues_on_clean_data(self):
        points = [make_point(float(i), source=f"s{i}") for i in range(20)]
        assert assess_data_quality(points, uuid4()).issues == []
