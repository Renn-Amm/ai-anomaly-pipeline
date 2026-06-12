# AI Anomaly Detection & Data Pipeline

> Real-time telemetry processing with automatic anomaly detection, data quality
> assessment, and persisted history — built with async FastAPI + SQLAlchemy.

[![CI Pipeline](https://github.com/your-org/ai-anomaly-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/ai-anomaly-pipeline/actions/workflows/ci.yml)
[![CodeQL](https://github.com/your-org/ai-anomaly-pipeline/actions/workflows/codeql.yml/badge.svg)](https://github.com/your-org/ai-anomaly-pipeline/actions/workflows/codeql.yml)
[![Coverage](https://img.shields.io/badge/coverage-91%25-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%20|%203.12-blue)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [What This Project Does](#what-this-project-does)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the App](#running-the-app)
- [Running with Docker](#running-with-docker)
- [API Reference](#api-reference)
- [Anomaly Detection Algorithms](#anomaly-detection-algorithms)
- [Data Quality Checks](#data-quality-checks)
- [Testing](#testing)
- [Configuration](#configuration)
- [Security](#security)
- [CI/CD Pipelines](#cicd-pipelines)
- [Setting Up the GitHub Repo](#setting-up-the-github-repo)
- [Contributing / PR Workflow](#contributing--pr-workflow)
- [Incident Knowledge Base](#incident-knowledge-base)
- [License](#license)

---

## What This Project Does

Telemetry sources (servers, sensors, services) send batches of numeric readings
to `POST /api/v1/telemetry`. The pipeline:

1. **Validates** every reading with strict Pydantic v2 models (rejects unknown
   fields, malformed metric names, oversized batches/tags).
2. **Runs data quality checks** — null/invalid ratio, duplicate ratio,
   out-of-range values — and assigns a `pass` / `warn` / `fail` flag.
3. **Runs four anomaly detectors concurrently** (Z-Score, IQR, absolute range,
   timestamp gaps), deduplicates results, and assigns a severity
   (`low` → `critical`).
4. **Persists** anomalies and quality reports to a database (SQLite by
   default, swappable to Postgres).
5. **Returns** the full result — anomalies + quality report + timing — in the
   same HTTP response, and makes history queryable via `/api/v1/anomalies`
   and `/api/v1/reports`.

Everything CPU-bound runs in a thread pool via `asyncio.gather`, so the event
loop stays free to handle concurrent requests — this is what lets the pipeline
scale horizontally without each component blocking the others.

---

## Architecture

```
                POST /api/v1/telemetry
                         │
                         ▼
        Pydantic validation (extra="forbid", regex-checked)
                         │
            ┌────────────┴────────────┐
            │  asyncio.gather (async)  │
            │  + ThreadPoolExecutor    │
            ▼                          ▼
   Data Quality Check          Anomaly Detection
   - null/NaN/Inf ratio        - Z-Score
   - duplicate ratio           - IQR (Tukey fences)
   - out-of-range count        - Absolute range
                                - Timestamp gaps
            │                          │
            └────────────┬─────────────┘
                          ▼
                 PipelineResult (JSON)
                          │
                          ▼
              SQLAlchemy async session
              ┌───────────┴───────────┐
              ▼                       ▼
        anomalies table       quality_reports table
              │                       │
              ▼                       ▼
   GET /api/v1/anomalies     GET /api/v1/reports
   GET /api/v1/reports/summary  (aggregated dashboard stats)
```

---

## Project Structure

```
ai-anomaly-pipeline/
├── app/
│   ├── main.py                    # FastAPI app, middleware, exception handling
│   ├── core/
│   │   ├── config.py              # Settings (env-driven, validated)
│   │   ├── database.py            # SQLAlchemy async engine, models, session
│   │   └── logging_config.py      # Structured logs, redacts secrets
│   ├── models/
│   │   └── schemas.py             # Pydantic request/response models
│   ├── services/
│   │   ├── anomaly_detector.py    # Z-Score, IQR, range, gap detectors
│   │   ├── data_quality.py        # Null/duplicate/range quality checks
│   │   └── pipeline.py            # Async orchestrator (gather + thread pool)
│   └── api/routes/
│       ├── health.py              # /health, /health/ready
│       ├── telemetry.py           # POST /api/v1/telemetry
│       ├── anomalies.py           # GET /api/v1/anomalies (filter/paginate)
│       └── reports.py             # GET /api/v1/reports, /reports/summary
├── tests/
│   ├── unit/                      # No I/O — pure function tests
│   │   ├── test_anomaly_detector.py
│   │   ├── test_data_quality.py
│   │   └── test_models.py
│   └── integration/               # Full app via httpx AsyncClient + LifespanManager
│       └── test_api.py
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Lint, security scan, tests, Docker build
│   │   ├── cd.yml                 # Build/push image, deploy staging → prod
│   │   ├── codeql.yml             # Weekly + per-PR SAST
│   │   └── security-audit.yml     # Weekly dependency CVE scan
│   ├── dependabot.yml              # Weekly dependency + Action updates
│   └── pull_request_template.md
├── docs/
│   └── github-security-setup.md   # Step-by-step repo hardening guide
├── Dockerfile                      # Multi-stage, non-root, healthcheck
├── requirements.txt
├── pyproject.toml                  # Ruff lint/format config
├── pytest.ini                      # Test config (80% coverage gate)
├── .env.example
├── .gitignore
└── README.md
```

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11 or 3.12 | Runtime |
| pip | latest | Dependency installation |
| Docker | optional | Containerized run/deploy |
| GitHub CLI (`gh`) | optional | Faster repo creation |
| Git | any recent | Version control |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ai-anomaly-pipeline.git
cd ai-anomaly-pipeline

# 2. (Recommended) Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template
cp .env.example .env
# Edit .env if you need to change thresholds, ports, or DATABASE_URL
```

> If you don't use a virtualenv on Debian/Ubuntu, you may need:
> `pip install -r requirements.txt --break-system-packages`

---

## Running the App

```bash
uvicorn app.main:app --reload
```

- Interactive API docs (Swagger UI): **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**
- Health check: **http://localhost:8000/health**

On first startup, the app automatically creates the SQLite database
(`pipeline.db`) and required tables — no migration step needed for local dev.

---

## Running with Docker

```bash
# Build
docker build -t ai-anomaly-pipeline .

# Run
docker run -p 8000:8000 --env-file .env ai-anomaly-pipeline

# Verify
curl http://localhost:8000/health
```

The image runs as a non-root user (`appuser`) and includes a built-in
`HEALTHCHECK` that polls `/health` every 30 seconds.

---

## API Reference

### `POST /api/v1/telemetry` — Submit a batch

```bash
curl -X POST http://localhost:8000/api/v1/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {"metric_name": "cpu_usage", "value": 52.1, "source": "server-01"},
      {"metric_name": "cpu_usage", "value": 51.8, "source": "server-01"},
      {"metric_name": "cpu_usage", "value": 9999.0, "source": "server-01"}
    ]
  }'
```

**Response (200):**

```json
{
  "batch_id": "a1b2c3d4-...",
  "status": "completed",
  "points_processed": 3,
  "anomalies_detected": 1,
  "anomalies": [
    {
      "metric_name": "cpu_usage",
      "value": 9999.0,
      "anomaly_type": "zscore",
      "severity": "critical",
      "score": 4.21,
      "description": "Z-score 4.21 exceeds threshold ±3.0 ...",
      "resolution_hint": "Verify sensor calibration. ..."
    }
  ],
  "quality_report": {
    "quality_flag": "pass",
    "null_ratio": 0.0,
    "duplicate_ratio": 0.0,
    "issues": []
  },
  "processing_time_ms": 3.4
}
```

### `GET /api/v1/anomalies` — Query anomaly history

| Query param | Type | Description |
|---|---|---|
| `severity` | `low\|medium\|high\|critical` | Filter by severity |
| `metric_name` | string | Filter by metric |
| `limit` | int (1–500, default 50) | Page size |
| `offset` | int (default 0) | Pagination offset |

```bash
curl "http://localhost:8000/api/v1/anomalies?severity=critical&limit=10"
```

### `GET /api/v1/reports` — Query quality report history

| Query param | Type | Description |
|---|---|---|
| `flag` | `pass\|warn\|fail` | Filter by quality flag |
| `limit`, `offset` | int | Pagination |

### `GET /api/v1/reports/summary` — Dashboard aggregate

```bash
curl http://localhost:8000/api/v1/reports/summary
```

```json
{
  "total_batches": 12,
  "total_anomalies": 7,
  "flag_counts": {"pass": 10, "warn": 2},
  "severity_counts": {"low": 3, "high": 2, "critical": 2}
}
```

### `GET /health` and `GET /health/ready`

Liveness and readiness probes for load balancers / Kubernetes.

---

## Anomaly Detection Algorithms

| Algorithm | Detects | Config key | Default |
|---|---|---|---|
| **Z-Score** | Points beyond N standard deviations from the batch mean | `ANOMALY_ZSCORE_THRESHOLD` | 3.0 |
| **IQR (Tukey)** | Points outside `Q1 - k·IQR` / `Q3 + k·IQR` | `ANOMALY_IQR_MULTIPLIER` | 1.5 |
| **Absolute Range** | Values outside a hard min/max | `VALUE_RANGE_MIN` / `VALUE_RANGE_MAX` | ±1,000,000 |
| **Timestamp Gap** | Missing readings / feed interruptions | hardcoded | 300 s |

Severity scales automatically with how far a value deviates from its
threshold: **low → medium → high → critical**. Results from all four
detectors are deduplicated on `(metric_name, timestamp, anomaly_type)`.

---

## Data Quality Checks

| Check | Warn threshold | Fail threshold | Config key |
|---|---|---|---|
| Null / NaN / Inf ratio | > 5% | > 10% | `MAX_NULL_RATIO` |
| Duplicate readings (same metric+timestamp+source) | > 2% | > 4% | `MAX_DUPLICATE_RATIO` |
| Out-of-range values | any → adds an issue | — | `VALUE_RANGE_MIN/MAX` |

---

## Testing

```bash
# Run everything with coverage
ENVIRONMENT=test python -m pytest tests/ -v

# Unit tests only (fast, no DB)
python -m pytest tests/unit/ -v

# Integration tests only (spins up the full app + in-memory DB)
ENVIRONMENT=test python -m pytest tests/integration/ -v
```

**Current status: 49/49 tests passing, 91% coverage** (gate: 80%).

Tests cover: detector math (including edge cases like constant series and
zero-IQR), Pydantic validation (rejecting bad input, oversized batches, extra
fields), full API round-trips, and persistence/query behavior for anomalies
and reports.

---

## Configuration

All configuration is via environment variables (see `.env.example`).
Never hardcode secrets — set them via `.env` locally or GitHub Secrets in CI/CD.

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development`, `staging`, `production`, `test` |
| `SECRET_KEY` | placeholder | Replace with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_HOSTS` | `["localhost","127.0.0.1"]` | TrustedHostMiddleware allow-list |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS allow-list |
| `DATABASE_URL` | `sqlite+aiosqlite:///./pipeline.db` | Swap for Postgres in production |
| `ANOMALY_ZSCORE_THRESHOLD` | `3.0` | Z-score cutoff |
| `ANOMALY_IQR_MULTIPLIER` | `1.5` | IQR fence multiplier |
| `MAX_NULL_RATIO` | `0.05` | Quality warn threshold |
| `MAX_DUPLICATE_RATIO` | `0.02` | Quality warn threshold |
| `VALUE_RANGE_MIN` / `MAX` | `±1,000,000` | Absolute sanity bounds |

---

## Security

- **Strict input validation** — Pydantic v2 `extra="forbid"`, regex-checked
  metric names, capped batch size (10,000) and tag counts (20).
- **Secrets never hardcoded** — all via environment variables; `.env` is
  gitignored.
- **Log redaction** — any log message containing `password`, `token`,
  `secret`, or `api_key` is automatically redacted.
- **Non-root container** — Dockerfile runs as `appuser`, multi-stage build
  with no compiler in the runtime image.
- **Dependency scanning** — `pip-audit` runs in CI and on a weekly schedule.
- **Static analysis** — `bandit` (Python SAST) on every PR.
- **CodeQL** — GitHub's deep security scanner runs weekly and on every PR.
- **Dependabot** — automatic PRs for vulnerable dependencies and GitHub
  Actions versions.

---

## CI/CD Pipelines

| Workflow | Trigger | Steps |
|---|---|---|
| `ci.yml` | Every push & PR to `main`/`develop` | Ruff lint+format → Bandit + pip-audit → pytest (matrix: 3.11, 3.12, 80% coverage gate) → Docker build |
| `cd.yml` | Push to `main` / tag `v*.*.*` | Build & push image to GHCR → deploy to staging → (on version tag) deploy to production |
| `codeql.yml` | PR + weekly | CodeQL security-and-quality analysis |
| `security-audit.yml` | Weekly (Mon 08:00 UTC) | `pip-audit` dependency CVE report |

All required checks must pass before a PR can be merged (see branch
protection setup below).

---

## Setting Up the GitHub Repo

```bash
cd ai-anomaly-pipeline
git init
git add .
git commit -m "feat: initial pipeline with persistence, CI/CD, and security"

# Create the repo (requires GitHub CLI, or do this via github.com UI)
gh repo create ai-anomaly-pipeline --private --source=. --remote=origin

git branch -M main
git push -u origin main
```

Then follow **[docs/github-security-setup.md](docs/github-security-setup.md)**
to configure, in order:

1. **Branch protection** on `main` — require PR + 1 approval, required status
   checks (`lint`, `test (3.12)`, `security`, `docker-build`), no force-push.
2. **Environments** — `staging` (1 reviewer) and `production` (2 reviewers,
   tag-gated), each with their own deploy-key secrets.
3. **Dependabot** — enable alerts + security updates (config already included).
4. **CodeQL** — enable code scanning (workflow already included).
5. **Secret scanning** — enable with push protection.

---

## Contributing / PR Workflow

```bash
git checkout -b feat/your-feature
# ... make changes, add tests ...
ENVIRONMENT=test python -m pytest tests/ -v   # must pass, ≥80% coverage
git push origin feat/your-feature
gh pr create --fill --base main
```

Use the PR template's security checklist — no secrets committed, input
validation for new endpoints, bandit clean.

---

## Incident Knowledge Base

| Anomaly Type | Likely Cause | Resolution |
|---|---|---|
| `zscore` (critical) | Sensor failure, data corruption | Check hardware; compare raw vs. processed feed |
| `iqr` (high) | Sudden load spike, config change | Review deploy history; check upstream services |
| `out_of_range` | Unit conversion bug, sensor saturation | Verify producer code and sensor spec range |
| `timestamp_gap` | Network interruption, producer crash | Check producer health and retry/backoff logic |

Quality flags:

| Flag | Meaning | Typical action |
|---|---|---|
| `pass` | No issues | None |
| `warn` | Null/duplicate ratio above warn threshold | Investigate source feed, no immediate outage |
| `fail` | Ratio more than 2× warn threshold | Treat as a data pipeline incident |

---

## License

MIT
