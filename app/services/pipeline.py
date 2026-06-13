"""
Pipeline Orchestrator
Coordinates data quality checks and anomaly detection.
Designed for async execution so it can run inside FastAPI without blocking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.models.schemas import PipelineResult, TelemetryBatch
from app.services.anomaly_detector import run_all_detectors
from app.services.data_quality import assess_data_quality

settings = get_settings()
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_WORKERS)


def _sanitize_for_log(value: object) -> str:
    """Return a log-safe representation by stripping line-break characters."""
    return str(value).replace("\r", "").replace("\n", "")


async def process_batch(batch: TelemetryBatch) -> PipelineResult:
    """
    Async pipeline entry point.
    CPU-bound work is offloaded to a thread pool so the event loop stays free.
    """
    start = time.perf_counter()
    loop = asyncio.get_event_loop()
    safe_batch_id = _sanitize_for_log(batch.batch_id)

    logger.info(f"Processing batch {safe_batch_id} " f"({len(batch.points)} points)")

    # Run quality and detection concurrently in threads
    quality_future = loop.run_in_executor(
        _executor,
        assess_data_quality,
        batch.points,
        batch.batch_id,
    )
    detection_future = loop.run_in_executor(
        _executor,
        run_all_detectors,
        batch.points,
        batch.batch_id,
    )

    quality_report, anomalies = await asyncio.gather(quality_future, detection_future)

    elapsed_ms = (time.perf_counter() - start) * 1000

    result = PipelineResult(
        batch_id=batch.batch_id,
        status="completed",
        points_processed=len(batch.points),
        anomalies_detected=len(anomalies),
        anomalies=anomalies,
        quality_report=quality_report,
        processing_time_ms=round(elapsed_ms, 2),
    )

    logger.info(
        f"Batch {safe_batch_id} done in {elapsed_ms:.1f}ms — "
        f"{len(anomalies)} anomalies, quality={quality_report.quality_flag.value}"
    )
    return result
