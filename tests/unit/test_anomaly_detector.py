"""
Unit tests — anomaly detection service.
All tests are deterministic and run without network or DB.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.models.schemas import TelemetryPoint
from app.services.anomaly_detector import (
    detect_zscore_anomalies,
    detect_iqr_anomalies,
    detect_out_of_range,
    detect_timestamp_gaps,
    run_all_detectors,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_point(value: float, metric: str = "cpu", offset_seconds: int = 0) -> TelemetryPoint:
    return TelemetryPoint(
        metric_name=metric,
        value=value,
        timestamp=datetime(2024, 1, 1, 12, 0, 0) + timedelta(seconds=offset_seconds),
        source="test-sensor",
    )


def normal_points(n: int = 100) -> list[TelemetryPoint]:
    """
    Readings centred around 50 with tiny sigma (0.3).
    With seed=7 and n=100, no sample should exceed ±3σ from the mean.
    """
    import random
    random.seed(7)
    return [make_point(50.0 + random.gauss(0, 0.3), offset_seconds=i * 10) for i in range(n)]


# ── Z-Score Tests ──────────────────────────────────────────────────────────────

class TestZScoreDetection:
    def test_no_anomalies_in_normal_data(self):
        points = normal_points()
        result = detect_zscore_anomalies(points, uuid4())
        assert len(result) == 0

    def test_detects_clear_spike(self):
        points = normal_points()
        points.append(make_point(9999.0, offset_seconds=1200))
        result = detect_zscore_anomalies(points, uuid4())
        assert any(a.value == 9999.0 for a in result)

    def test_too_few_points_returns_empty(self):
        points = [make_point(1.0), make_point(2.0)]
        result = detect_zscore_anomalies(points, uuid4())
        assert result == []

    def test_constant_series_returns_empty(self):
        points = [make_point(5.0, offset_seconds=i) for i in range(20)]
        result = detect_zscore_anomalies(points, uuid4())
        assert result == []

    def test_custom_threshold_respected(self):
        points = normal_points()
        points.append(make_point(60.0, offset_seconds=1200))  # mild spike
        tight = detect_zscore_anomalies(points, uuid4(), threshold=1.0)
        loose = detect_zscore_anomalies(points, uuid4(), threshold=10.0)
        assert len(tight) > len(loose)

    def test_anomaly_record_has_score(self):
        points = normal_points()
        points.append(make_point(9999.0, offset_seconds=1200))
        result = detect_zscore_anomalies(points, uuid4())
        assert result[0].score is not None
        assert result[0].score > 3.0

    def test_batch_id_propagated(self):
        batch_id = uuid4()
        points = normal_points()
        points.append(make_point(9999.0, offset_seconds=1200))
        result = detect_zscore_anomalies(points, batch_id)
        assert all(a.batch_id == batch_id for a in result)


# ── IQR Tests ──────────────────────────────────────────────────────────────────

class TestIQRDetection:
    def test_no_anomalies_in_normal_data(self):
        """
        With a very tight 0.3σ distribution the IQR fence is narrow;
        use a large multiplier so normal values never cross it.
        """
        points = normal_points()
        result = detect_iqr_anomalies(points, uuid4(), multiplier=10.0)
        assert len(result) == 0

    def test_detects_outlier(self):
        points = [make_point(float(v), offset_seconds=i) for i, v in enumerate([10, 11, 10, 12, 11, 10, 200])]
        result = detect_iqr_anomalies(points, uuid4())
        assert any(a.value == 200.0 for a in result)

    def test_too_few_points(self):
        points = [make_point(1.0), make_point(2.0), make_point(3.0)]
        result = detect_iqr_anomalies(points, uuid4())
        assert result == []


# ── Out-of-Range Tests ─────────────────────────────────────────────────────────

class TestOutOfRangeDetection:
    def test_within_range_passes(self):
        points = [make_point(0.0), make_point(100.0)]
        result = detect_out_of_range(points, uuid4(), min_val=-1000.0, max_val=1000.0)
        assert result == []

    def test_below_min_flagged(self):
        points = [make_point(-9_000_000.0)]
        result = detect_out_of_range(points, uuid4())
        assert len(result) == 1

    def test_above_max_flagged(self):
        points = [make_point(9_000_000.0)]
        result = detect_out_of_range(points, uuid4())
        assert len(result) == 1


# ── Timestamp Gap Tests ────────────────────────────────────────────────────────

class TestTimestampGapDetection:
    def test_regular_intervals_pass(self):
        points = [make_point(1.0, offset_seconds=i * 60) for i in range(10)]
        result = detect_timestamp_gaps(points, uuid4(), max_gap_seconds=300)
        assert result == []

    def test_large_gap_detected(self):
        base = datetime(2024, 1, 1, 12, 0, 0)
        points = [
            TelemetryPoint(metric_name="temp", value=1.0, timestamp=base, source="s"),
            TelemetryPoint(
                metric_name="temp",
                value=2.0,
                timestamp=base + timedelta(seconds=3600),
                source="s",
            ),
        ]
        result = detect_timestamp_gaps(points, uuid4(), max_gap_seconds=300)
        assert len(result) == 1
        assert result[0].score == 3600.0

    def test_single_point_returns_empty(self):
        result = detect_timestamp_gaps([make_point(1.0)], uuid4())
        assert result == []


# ── Combined Detector Tests ────────────────────────────────────────────────────

class TestRunAllDetectors:
    def test_runs_without_error_on_normal_data(self):
        points = normal_points()
        result = run_all_detectors(points, uuid4())
        assert isinstance(result, list)

    def test_deduplication(self):
        """Same (metric, timestamp, type) key must not appear twice."""
        points = normal_points()
        points.append(make_point(9_999_999.0, offset_seconds=2000))
        result = run_all_detectors(points, uuid4())
        keys = [(a.metric_name, a.timestamp, a.anomaly_type) for a in result]
        assert len(keys) == len(set(keys))
