"""
Structured logging — JSON in production, human-readable in dev.
No sensitive values (tokens, keys, PII) are ever logged.
"""

import logging
import sys

from app.core.config import get_settings

settings = get_settings()


class SensitiveDataFilter(logging.Filter):
    """Strip known sensitive patterns from log records."""

    REDACT_KEYS = {"password", "secret", "token", "api_key", "authorization"}

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            lower = record.msg.lower()
            for key in self.REDACT_KEYS:
                if key in lower:
                    record.msg = "[REDACTED — sensitive field]"
                    break
        return True


def setup_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SensitiveDataFilter())

    if settings.ENVIRONMENT == "production":
        try:
            import json_log_formatter  # type: ignore[import]
            formatter = json_log_formatter.JSONFormatter()
        except ImportError:
            formatter = logging.Formatter(
                '{"time":"%(asctime)s","level":"%(levelname)s",'
                '"name":"%(name)s","msg":"%(message)s"}'
            )
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    for noisy in ("uvicorn.access", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)