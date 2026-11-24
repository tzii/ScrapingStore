"""Compatibility shim for the 2.x ``generate_dashboard(..., terminal_path=...)`` call."""

import warnings
from typing import Optional

from scrapingstore.report.generator import ReportSource
from scrapingstore.report.generator import generate_dashboard as _generate_dashboard


def generate_dashboard(
    source: ReportSource,
    output_path: Optional[str] = None,
    terminal_path: Optional[str] = None,
    **kwargs,
) -> str:
    """Write the HTML report. ``terminal_path`` is accepted for 2.x callers and ignored."""
    if terminal_path is not None:
        warnings.warn(
            "terminal_path is ignored: ScrapingStore 3 writes a single report.",
            DeprecationWarning,
            stacklevel=2,
        )
    return _generate_dashboard(source, output_path, **kwargs)


__all__ = ["generate_dashboard"]
