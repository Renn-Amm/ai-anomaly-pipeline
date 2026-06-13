"""
Persistence layer — async SQLAlchemy with SQLite (swap DATABASE_URL for Postgres).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()
Base = declarative_base()

_engine_kwargs: dict = {"echo": False}
if ":memory:" in settings.DATABASE_URL:
    _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class AnomalyORM(Base):
    __tablename__ = "anomalies"

    id = Column(String(36), primary_key=True)
    batch_id = Column(String(36), index=True, nullable=False)
    metric_name = Column(String(128), index=True, nullable=False)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    anomaly_type = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False, index=True)
    score = Column(Float, nullable=True)
    description = Column(String(512), nullable=False)
    resolution_hint = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class QualityReportORM(Base):
    __tablename__ = "quality_reports"

    batch_id = Column(String(36), primary_key=True)
    total_points = Column(Integer, nullable=False)
    null_count = Column(Integer, nullable=False)
    duplicate_count = Column(Integer, nullable=False)
    out_of_range_count = Column(Integer, nullable=False)
    null_ratio = Column(Float, nullable=False)
    duplicate_ratio = Column(Float, nullable=False)
    quality_flag = Column(String(8), nullable=False, index=True)
    issues = Column(JSON, nullable=False, default=list)
    processed_at = Column(DateTime, default=lambda: datetime.now(UTC))


async def init_db() -> None:
    """Create tables on startup — idempotent."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        yield session


async def save_pipeline_result(session: AsyncSession, result) -> None:
    """Persist anomalies + quality report from a PipelineResult."""
    for a in result.anomalies:
        session.add(
            AnomalyORM(
                id=str(a.anomaly_id),
                batch_id=str(a.batch_id),
                metric_name=a.metric_name,
                value=a.value,
                timestamp=a.timestamp,
                anomaly_type=a.anomaly_type.value,
                severity=a.severity.value,
                score=a.score,
                description=a.description,
                resolution_hint=a.resolution_hint,
            )
        )
    qr = result.quality_report
    session.add(
        QualityReportORM(
            batch_id=str(qr.batch_id),
            total_points=qr.total_points,
            null_count=qr.null_count,
            duplicate_count=qr.duplicate_count,
            out_of_range_count=qr.out_of_range_count,
            null_ratio=qr.null_ratio,
            duplicate_ratio=qr.duplicate_ratio,
            quality_flag=qr.quality_flag.value,
            issues=qr.issues,
        )
    )
    await session.commit()