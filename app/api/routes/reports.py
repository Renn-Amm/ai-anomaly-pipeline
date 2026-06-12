"""Data quality report endpoints — backed by SQLite/Postgres."""

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AnomalyORM, QualityReportORM, get_session
from app.models.schemas import QualityFlag

router = APIRouter()


class QualityReportOut(BaseModel):
    batch_id: UUID
    total_points: int
    null_count: int
    duplicate_count: int
    out_of_range_count: int
    null_ratio: float
    duplicate_ratio: float
    quality_flag: QualityFlag
    issues: List[str]
    processed_at: datetime

    model_config = {"from_attributes": True}


class QualityReportListResponse(BaseModel):
    total: int
    items: List[QualityReportOut]


class SummaryResponse(BaseModel):
    total_batches: int
    total_anomalies: int
    flag_counts: dict
    severity_counts: dict


@router.get("/reports", response_model=QualityReportListResponse)
async def list_reports(
    flag: QualityFlag | None = Query(None, description="Filter by quality flag"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Retrieve data quality reports for previously processed batches, newest first."""
    stmt = select(QualityReportORM).order_by(QualityReportORM.processed_at.desc())
    if flag is not None:
        stmt = stmt.where(QualityReportORM.quality_flag == flag.value)

    total = len((await session.execute(stmt)).scalars().all())
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()

    items = [
        QualityReportOut(
            batch_id=UUID(r.batch_id),
            total_points=r.total_points,
            null_count=r.null_count,
            duplicate_count=r.duplicate_count,
            out_of_range_count=r.out_of_range_count,
            null_ratio=r.null_ratio,
            duplicate_ratio=r.duplicate_ratio,
            quality_flag=QualityFlag(r.quality_flag),
            issues=r.issues or [],
            processed_at=r.processed_at,
        )
        for r in rows
    ]
    return QualityReportListResponse(total=total, items=items)


@router.get("/reports/summary", response_model=SummaryResponse)
async def reports_summary(session: AsyncSession = Depends(get_session)):
    """Aggregate counts across all processed batches — useful for dashboards."""
    total_batches = (
        await session.execute(select(func.count(QualityReportORM.batch_id)))
    ).scalar_one()

    total_anomalies = (
        await session.execute(select(func.count(AnomalyORM.id)))
    ).scalar_one()

    flag_rows = await session.execute(
        select(QualityReportORM.quality_flag, func.count())
        .group_by(QualityReportORM.quality_flag)
    )
    flag_counts = {row[0]: row[1] for row in flag_rows.all()}

    severity_rows = await session.execute(
        select(AnomalyORM.severity, func.count())
        .group_by(AnomalyORM.severity)
    )
    severity_counts = {row[0]: row[1] for row in severity_rows.all()}

    return SummaryResponse(
        total_batches=total_batches,
        total_anomalies=total_anomalies,
        flag_counts=flag_counts,
        severity_counts=severity_counts,
    )
