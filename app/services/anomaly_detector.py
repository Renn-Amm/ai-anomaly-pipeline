"""
Anomaly Detection Service
Supports: Z-Score, IQR, out-of-range, and timestamp-gap detection.
All algorithms are stateless and deterministic for testability.
"""

from __future__ import annotations

import logging
import statistics
from uuid import UUID

from app.core.config import get_settings
from app.models.schemas import AnomalyRecord, AnomalyType, Severity, TelemetryPoint

settings = get_settings()
logger = logging.getLogger(__name__)


def _classify_severity(score: float, threshold: float) -> Severity:
    ratio = abs(score) / threshold
    if ratio >= 3.0:
        return Severity.CRITICAL
    if ratio >= 2.0:
        return Severity.HIGH
    if ratio >= 1.5:
        return Severity.MEDIUM
    return Severity.LOW


def detect_zscore_anomalies(
    points: list[TelemetryPoint],
    batch_id: UUID,
    threshold: float | None = None,
) -> list[AnomalyRecord]:
    """Flag points whose z-score exceeds the configured threshold."""
    threshold = threshold or settings.ANOMALY_ZSCORE_THRESHOLD
    anomalies: list[AnomalyRecord] = []

    if len(points) < 3:
        return anomalies

    values = [p.value for p in points]
    try:
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
    except statistics.StatisticsError:
        return anomalies

    if stdev == 0:
        return anomalies

    for point in points:
        z = (point.value - mean) / stdev
        if abs(z) > threshold:
            anomalies.append(
                AnomalyRecord(
                    batch_id=batch_id,
                    metric_name=point.metric_name,
                    value=point.value,
                    timestamp=point.timestamp,
                    anomaly_type=AnomalyType.ZSCORE,
                    severity=_classify_severity(z, threshold),
                    score=round(z, 4),
                    description=(
                        f"Z-score {z:.2f} exceeds threshold ±{threshold} "
                        f"(mean={mean:.2f}, σ={stdev:.2f})"
                    ),
                    resolution_hint=(
                        "Verify sensor calibration. Check for upstream "
                        "configuration changes or data feed interruptions."
                    ),
                )
            )

    logger.info("Z-score: %d anomalies in %d points", len(anomalies), len(points))
    return anomalies


def detect_iqr_anomalies(
    points: list[TelemetryPoint],
    batch_id: UUID,
    multiplier: float | None = None,
) -> list[AnomalyRecord]:
    """Flag points outside the IQR fence (Tukey method)."""
    multiplier = multiplier or settings.ANOMALY_IQR_MULTIPLIER
    anomalies: list[AnomalyRecord] = []

    if len(points) < 4:
        return anomalies

    values = sorted(p.value for p in points)
    n = len(values)
    q1 = statistics.median(values[: n // 2])
    q3 = statistics.median(values[n // 2 + (n % 2) :])
    iqr = q3 - q1

    if iqr == 0:
        return anomalies

    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    for point in points:
        if point.value < lower or point.value > upper:
            dev = (
                (point.value - upper) / iqr
                if point.value > upper
                else (lower - point.value) / iqr
            )
            anomalies.append(
                AnomalyRecord(
                    batch_id=batch_id,
                    metric_name=point.metric_name,
                    value=point.value,
                    timestamp=point.timestamp,
                    anomaly_type=AnomalyType.IQR,
                    severity=_classify_severity(dev, 1.0),
                    score=round(dev, 4),
                    description=(
                        f"Value {point.value} outside IQR fence "
                        f"[{lower:.2f}, {upper:.2f}] "
                        f"(Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f})"
                    ),
                    resolution_hint=(
                        "Inspect raw data source for sudden spikes. "
                        "Consider smoothing or rate-limiting the feed."
                    ),
                )
            )

    logger.info("IQR: %d anomalies in %d points", len(anomalies), len(points))
    return anomalies


def detect_out_of_range(
    points: list[TelemetryPoint],
    batch_id: UUID,
    min_val: float | None = None,
    max_val: float | None = None,
) -> list[AnomalyRecord]:
    """Flag values outside the configured absolute range."""
    min_val = min_val if min_val is not None else settings.VALUE_RANGE_MIN
    max_val = max_val if max_val is not None else settings.VALUE_RANGE_MAX
    anomalies: list[AnomalyRecord] = []

    for point in points:
        if point.value < min_val or point.value > max_val:
            anomalies.append(
                AnomalyRecord(
                    batch_id=batch_id,
                    metric_name=point.metric_name,
                    value=point.value,
                    timestamp=point.timestamp,
                    anomaly_type=AnomalyType.OUT_OF_RANGE,
                    severity=Severity.HIGH,
                    description=(
                        f"Value {point.value} outside allowed range "
                        f"[{min_val}, {max_val}]"
                    ),
                    resolution_hint=(
                        "Check sensor hardware for saturation or failure. "
                        "Verify unit conversions in the data producer."
                    ),
                )
            )

    return anomalies


def detect_timestamp_gaps(
    points: list[TelemetryPoint],
    batch_id: UUID,
    max_gap_seconds: float = 300.0,
) -> list[AnomalyRecord]:
    """Flag large time gaps between consecutive readings."""
    anomalies: list[AnomalyRecord] = []
    if len(points) < 2:
        return anomalies

    sorted_points = sorted(points, key=lambda p: p.timestamp)
    for i in range(1, len(sorted_points)):
        prev = sorted_points[i - 1]
        curr = sorted_points[i]
        gap = (curr.timestamp - prev.timestamp).total_seconds()
        if gap > max_gap_seconds:
            anomalies.append(
                AnomalyRecord(
                    batch_id=batch_id,
                    metric_name=curr.metric_name,
                    value=gap,
                    timestamp=curr.timestamp,
                    anomaly_type=AnomalyType.TIMESTAMP_GAP,
                    severity=Severity.MEDIUM if gap < 900 else Severity.HIGH,
                    score=round(gap, 2),
                    description=(
                        f"Gap of {gap:.0f}s between readings "
                        f"(threshold: {max_gap_seconds}s)"
                    ),
                    resolution_hint=(
                        "Check network connectivity and producer health. "
                        "Review retry logic in the telemetry sender."
                    ),
                )
            )

    return anomalies


def run_all_detectors(
    points: list[TelemetryPoint],
    batch_id: UUID,
) -> list[AnomalyRecord]:
    """Run every detector and deduplicate by (metric, timestamp, type)."""
    all_anomalies: list[AnomalyRecord] = []
    all_anomalies.extend(detect_zscore_anomalies(points, batch_id))
    all_anomalies.extend(detect_iqr_anomalies(points, batch_id))
    all_anomalies.extend(detect_out_of_range(points, batch_id))
    all_anomalies.extend(detect_timestamp_gaps(points, batch_id))

    seen: set[tuple] = set()
    unique: list[AnomalyRecord] = []
    for a in all_anomalies:
        key = (a.metric_name, a.timestamp, a.anomaly_type)
        if key not in seen:
            seen.add(key)
            unique.append(a)

    logger.info(
        "Detection complete: %d unique anomalies from %d points",
        len(unique),
        len(points),
    )
    return unique
