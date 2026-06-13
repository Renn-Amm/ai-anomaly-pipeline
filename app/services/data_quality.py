"""
Data Quality Service
Checks null ratios, duplicates, and value ranges.
"""

from __future__ import annotations

import logging
import math
from uuid import UUID

from app.core.config import get_settings
from app.models.schemas import DataQualityReport, QualityFlag, TelemetryPoint

settings = get_settings()
logger = logging.getLogger(__name__)


def assess_data_quality(
    points: list[TelemetryPoint],
    batch_id: UUID,
) -> DataQualityReport:
    """Run all quality checks. Returns PASS | WARN | FAIL."""
    total = len(points)
    issues: list[str] = []

    null_count = sum(
        1 for p in points if p.value is None or math.isnan(p.value) or math.isinf(p.value)
    )
    null_ratio = null_count / total if total else 0.0

    seen_keys: set[tuple] = set()
    dup_count = 0
    for p in points:
        key = (p.metric_name, p.timestamp.isoformat(), p.source)
        if key in seen_keys:
            dup_count += 1
        else:
            seen_keys.add(key)
    dup_ratio = dup_count / total if total else 0.0

    oor_count = sum(
        1
        for p in points
        if p.value < settings.VALUE_RANGE_MIN or p.value > settings.VALUE_RANGE_MAX
    )

    if null_ratio > settings.MAX_NULL_RATIO:
        issues.append(
            f"High null/invalid ratio: {null_ratio:.1%} "
            f"(threshold: {settings.MAX_NULL_RATIO:.1%})"
        )
    if dup_ratio > settings.MAX_DUPLICATE_RATIO:
        issues.append(
            f"High duplicate ratio: {dup_ratio:.1%} "
            f"(threshold: {settings.MAX_DUPLICATE_RATIO:.1%})"
        )
    if oor_count > 0:
        issues.append(f"{oor_count} value(s) outside allowed range")

    if null_ratio > settings.MAX_NULL_RATIO * 2 or dup_ratio > settings.MAX_DUPLICATE_RATIO * 2:
        flag = QualityFlag.FAIL
    elif issues:
        flag = QualityFlag.WARN
    else:
        flag = QualityFlag.PASS

    logger.info(
        "Quality: flag=%s nulls=%d dups=%d oor=%d",
        flag.value,
        null_count,
        dup_count,
        oor_count,
    )
    return DataQualityReport(
        batch_id=batch_id,
        total_points=total,
        null_count=null_count,
        duplicate_count=dup_count,
        out_of_range_count=oor_count,
        null_ratio=round(null_ratio, 6),
        duplicate_ratio=round(dup_ratio, 6),
        quality_flag=flag,
        issues=issues,
    )
