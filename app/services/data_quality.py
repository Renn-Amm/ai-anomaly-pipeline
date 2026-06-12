"""
Data Quality Service
Checks null ratios, duplicates, and value ranges.
Returns a structured quality report with pass/warn/fail flags.
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from app.core.config import get_settings
from app.models.schemas import DataQualityReport, QualityFlag, TelemetryPoint

settings = get_settings()
logger = logging.getLogger(__name__)


def assess_data_quality(
    points: List[TelemetryPoint],
    batch_id: UUID,
) -> DataQualityReport:
    """
    Run all quality checks on a batch of telemetry points.
    Returns a DataQualityReport with flag = PASS | WARN | FAIL.
    """
    total = len(points)
    issues: List[str] = []

    # ── Null / NaN values ─────────────────────────────────────────────────────
    import math
    null_count = sum(
        1 for p in points if p.value is None or math.isnan(p.value) or math.isinf(p.value)
    )
    null_ratio = null_count / total if total else 0.0

    # ── Duplicates (same metric_name + timestamp) ─────────────────────────────
    seen_keys: set = set()
    dup_count = 0
    for p in points:
        key = (p.metric_name, p.timestamp.isoformat(), p.source)
        if key in seen_keys:
            dup_count += 1
        else:
            seen_keys.add(key)
    dup_ratio = dup_count / total if total else 0.0

    # ── Out of absolute range ─────────────────────────────────────────────────
    oor_count = sum(
        1 for p in points
        if p.value < settings.VALUE_RANGE_MIN or p.value > settings.VALUE_RANGE_MAX
    )

    # ── Build issue messages ───────────────────────────────────────────────────
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

    # ── Assign quality flag ────────────────────────────────────────────────────
    if null_ratio > settings.MAX_NULL_RATIO * 2 or dup_ratio > settings.MAX_DUPLICATE_RATIO * 2:
        flag = QualityFlag.FAIL
    elif issues:
        flag = QualityFlag.WARN
    else:
        flag = QualityFlag.PASS

    logger.info(
        f"Quality assessment: flag={flag.value}, "
        f"nulls={null_count}, dups={dup_count}, oor={oor_count}"
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
