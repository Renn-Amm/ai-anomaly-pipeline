"""Anomaly query endpoints — backed by SQLite/Postgres via SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AnomalyORM, get_session
from app.models.schemas import AnomalyType, Severity

router = APIRouter()


class AnomalyOut(BaseModel):
    anomaly_id: UUID
    batch_id: UUID
    metric_name: str
    value: float
    timestamp: datetime
    anomaly_type: AnomalyType
    severity: Severity
    score: float | None = None
    description: str
    resolution_hint: str

    model_config = {"from_attributes": True}


class AnomalyListResponse(BaseModel):
    total: int
    items: list[AnomalyOut]


@router.get("/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
    severity: Severity | None = Query(None, description="Filter by severity"),
    metric_name: str | None = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> AnomalyListResponse:
    """Retrieve detected anomalies, newest first. Filter and paginate."""
    filters = []
    if severity is not None:
        filters.append(AnomalyORM.severity == severity.value)
    if metric_name is not None:
        filters.append(AnomalyORM.metric_name == metric_name)

    count_stmt = select(func.count(AnomalyORM.id))
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = select(AnomalyORM).order_by(AnomalyORM.created_at.desc())
    for f in filters:
        stmt = stmt.where(f)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()

    items = [
        AnomalyOut(
            anomaly_id=UUID(r.id),
            batch_id=UUID(r.batch_id),
            metric_name=r.metric_name,
            value=r.value,
            timestamp=r.timestamp,
            anomaly_type=AnomalyType(r.anomaly_type),
            severity=Severity(r.severity),
            score=r.score,
            description=r.description,
            resolution_hint=r.resolution_hint,
        )
        for r in rows
    ]
    return AnomalyListResponse(total=total, items=items)