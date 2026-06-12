"""
AI Anomaly Detection & Data Pipeline
Main FastAPI application entry point
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, telemetry, anomalies, reports
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging_config import setup_logging

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — startup and shutdown."""
    logger.info("Starting AI Anomaly Detection Pipeline...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    await init_db()
    yield
    logger.info("Shutting down AI Anomaly Detection Pipeline...")


app = FastAPI(
    title="AI Anomaly Detection & Data Pipeline",
    description=(
        "Real-time telemetry data pipeline with anomaly detection and "
        "data quality flagging. Built with async FastAPI for scale."
    ),
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)

_allowed_hosts = settings.ALLOWED_HOSTS
if settings.ENVIRONMENT in ("development", "test"):
    _allowed_hosts = ["*"]  # allow httpx test client host
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    logger.debug(
        "request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

app.include_router(health.router, tags=["Health"])
app.include_router(telemetry.router, prefix="/api/v1", tags=["Telemetry"])
app.include_router(anomalies.router, prefix="/api/v1", tags=["Anomalies"])
app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])
