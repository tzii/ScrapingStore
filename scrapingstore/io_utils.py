"""Atomic filesystem writes, UTC helpers, stable JSON, and CSV safety."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize naive or offset datetimes into UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def stable_json(value: Any) -> str:
    """Deterministic JSON encoding rejecting NaN/Infinity."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def escape_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection (=, +, -, @, tab, CR)."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def atomic_write_bytes(destination: Path | str, data: bytes) -> Path:
    """Write bytes to a sibling temp file and atomically replace destination."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def atomic_write_text(
    destination: Path | str, text: str, *, encoding: str = "utf-8"
) -> Path:
    """Atomically write UTF-8 text to destination."""
    return atomic_write_bytes(destination, text.encode(encoding))
