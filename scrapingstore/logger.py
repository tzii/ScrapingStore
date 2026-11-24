"""Unified Rich and structured JSON logging for ScrapingStore."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from rich.logging import RichHandler


class JsonLogFormatter(logging.Formatter):
    """Single-line JSON log formatter for CI/automation pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logger(level: str = "INFO", *, json_logs: bool = False) -> None:
    """Configure root logging with either Rich console output or JSON lines."""
    handler: logging.Handler
    if json_logs:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonLogFormatter())
    else:
        handler = RichHandler(rich_tracebacks=True, show_path=False)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
