"""Anomaly query endpoints — backed by SQLite/Postgres via SQLAlchemy."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
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
    score: Optional[float] = None
    description: str
    resolution_hint: str

    model_config = {"from_attributes": True}


class AnomalyListResponse(BaseModel):
    total: int
    items: List[AnomalyOut]


@router.get("/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
    severity: Optional[Severity] = Query(None, description="Filter by severity"),
    metric_name: Optional[str] = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """
    Retrieve previously detected anomalies, newest first.
    Filter by severity and/or metric_name; paginate with limit/offset.
    """
    stmt = select(AnomalyORM).order_by(AnomalyORM.created_at.desc())

    if severity is not None:
        stmt = stmt.where(AnomalyORM.severity == severity.value)
    if metric_name is not None:
        stmt = stmt.where(AnomalyORM.metric_name == metric_name)

    total = len((await session.execute(stmt)).scalars().all())

    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()

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
