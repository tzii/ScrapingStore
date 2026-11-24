"""Compatibility shim for the removed 2.x terminal-style report."""

import warnings
from typing import Optional

from scrapingstore.config import get_settings
from scrapingstore.report.generator import ReportSource, generate_dashboard


def generate_terminal_dashboard(
    source: ReportSource,
    output_path: Optional[str] = None,
    dashboard_path: Optional[str] = None,
) -> str:
    """Deprecated: writes the standard report to the old terminal-report path."""
    warnings.warn(
        "The terminal-style report was removed in ScrapingStore 3; "
        "generate_terminal_dashboard now writes the standard report.",
        DeprecationWarning,
        stacklevel=2,
    )
    destination = output_path or str(get_settings().data_dir / "dashboard_terminal.html")
    return generate_dashboard(source, destination)


__all__ = ["generate_terminal_dashboard"]
