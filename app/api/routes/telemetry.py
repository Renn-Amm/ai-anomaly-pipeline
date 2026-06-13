"""Telemetry ingestion endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session, save_pipeline_result
from app.core.security import require_api_key
from app.models.schemas import PipelineResult, TelemetryBatch
from app.services.pipeline import process_batch

router = APIRouter()


@router.post(
    "/telemetry",
    response_model=PipelineResult,
    status_code=status.HTTP_200_OK,
    summary="Submit a telemetry batch for processing",
    dependencies=[Depends(require_api_key)],
)
async def ingest_telemetry(
    batch: TelemetryBatch,
    session: AsyncSession = Depends(get_session),
) -> PipelineResult:
    """
    Submit a batch of telemetry readings.
    Runs data quality checks and anomaly detection concurrently, persists
    the results, and returns the full result in the same request.
    """
    try:
        result = await process_batch(batch)
        await save_pipeline_result(session, result)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline processing failed. Check logs for details.",
        ) from exc