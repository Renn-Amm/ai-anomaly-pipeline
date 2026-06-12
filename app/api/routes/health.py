"""Health check endpoints — used by load balancers and CI smoke tests."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness probe — returns 200 when the process is running."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
    )


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness probe — extend here to check DB / queue connectivity."""
    return HealthResponse(
        status="ready",
        timestamp=datetime.utcnow(),
        version="1.0.0",
    )
