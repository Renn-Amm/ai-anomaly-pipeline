"""Unit tests — data quality service."""

import math
import pytest
from datetime import datetime
from uuid import uuid4

from app.models.schemas import QualityFlag, TelemetryPoint
from app.services.data_quality import assess_data_quality


def make_point(value: float, metric: str = "m", source: str = "s") -> TelemetryPoint:
    return TelemetryPoint(
        metric_name=metric,
        value=value,
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        source=source,
    )


class TestDataQuality:
    def test_clean_batch_passes(self):
        points = [make_point(float(i), source=f"s{i}") for i in range(100)]
        report = assess_data_quality(points, uuid4())
        assert report.quality_flag == QualityFlag.PASS
        assert report.total_points == 100
        assert report.null_count == 0
        assert report.duplicate_count == 0

    def test_flags_high_null_ratio(self):
        points = [make_point(float(i), source=f"s{i}") for i in range(90)]
        # Simulate invalid values by adding inf values
        for i in range(10):
            points.append(TelemetryPoint(
                metric_name="m",
                value=math.inf,
                timestamp=datetime(2024, 1, 1, 12, 0, i + 1),
                source=f"bad{i}",
            ))
        report = assess_data_quality(points, uuid4())
        assert report.null_count == 10
        assert report.null_ratio > 0.05
        assert report.quality_flag in (QualityFlag.WARN, QualityFlag.FAIL)

    def test_flags_duplicates(self):
        base = make_point(1.0)
        points = [base] * 10  # all identical — 9 duplicates
        report = assess_data_quality(points, uuid4())
        assert report.duplicate_count == 9

    def test_out_of_range_counted(self):
        points = [make_point(1.0, source=f"s{i}") for i in range(10)]
        points.append(TelemetryPoint(
            metric_name="m",
            value=9_000_000.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 1),
            source="oor",
        ))
        report = assess_data_quality(points, uuid4())
        assert report.out_of_range_count == 1

    def test_batch_id_in_report(self):
        batch_id = uuid4()
        points = [make_point(1.0, source="s1")]
        report = assess_data_quality(points, batch_id)
        assert report.batch_id == batch_id

    def test_empty_issues_on_clean_data(self):
        points = [make_point(float(i), source=f"s{i}") for i in range(20)]
        report = assess_data_quality(points, uuid4())
        assert report.issues == []
