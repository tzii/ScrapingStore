"""Compatibility shim re-exporting scrapingstore.report.snapshot."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from scrapingstore.report.snapshot import (
    ReportSnapshot,
    _normalize_row,
)
from scrapingstore.report.snapshot import (
    _build_context as _core_build_context,
)


def report_link(destination: Path, sibling: Path) -> str:
    """Build a browser link from one report file to another (kept for 2.x callers)."""
    relative = os.path.relpath(Path(sibling).resolve(), Path(destination).resolve().parent)
    return quote(Path(relative).as_posix(), safe="/")


def _normalize_products_df(df: Any) -> List[Dict[str, Any]]:
    """Convert a DataFrame or sequence of dicts into normalized product rows."""
    if hasattr(df, "to_dict"):
        records = df.to_dict(orient="records")
    else:
        records = list(df)
    return [_normalize_row(r) for r in records]


def _build_context(
    rows: Any, generated_at: Optional[Any] = None
) -> Dict[str, Any]:
    if hasattr(rows, "to_dict"):
        rows = _normalize_products_df(rows)
    return _core_build_context(rows, generated_at=generated_at)


__all__ = [
    "ReportSnapshot",
    "_build_context",
    "_normalize_products_df",
    "report_link",
]
