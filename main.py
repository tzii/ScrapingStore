"""Compatibility entrypoint forwarding to scrapingstore.cli.app."""

import warnings
from typing import Optional

import scrapingstore.cli.app as _cli
from scrapingstore.cli.app import (
    ScraperType,
    SourceKind,
    _create_scraper,
    _generate_pipeline_dashboard,
    _persist_collection,
    _publish_collection,
    app,
)
from scrapingstore.config import get_settings
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.sources.results import clean_products
from scrapingstore.transport.browser import BrowserScraper
from scrapingstore.transport.http import StaticScraper
from visualization.dashboard_generator import generate_dashboard
from visualization.terminal_dashboard_generator import generate_terminal_dashboard

_s = get_settings()
BASE_URL = _s.base_url
DATA_DIR = _s.data_dir
DASHBOARD_HTML_PATH = _s.dashboard_html_path
DOCS_DASHBOARD_HTML_PATH = _s.docs_dashboard_html_path
# The terminal-style report was removed in 3.0; these paths are kept for old imports.
TERMINAL_DASHBOARD_HTML_PATH = _s.data_dir / "dashboard_terminal.html"
DOCS_TERMINAL_DASHBOARD_HTML_PATH = _s.docs_dir / "dashboard_terminal.html"


def _generate_pipeline_dashboards(
    db: DatabaseManager,
    dashboard_path: Optional[str] = None,
    terminal_path: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """Deprecated 2.x helper: writes the single report; ``terminal_path`` is ignored."""
    if terminal_path is not None:
        warnings.warn(
            "terminal_path is ignored: ScrapingStore 3 writes a single report.",
            DeprecationWarning,
            stacklevel=2,
        )
    _generate_pipeline_dashboard(db, dashboard_path, run_id)


__all__ = [
    "BASE_URL",
    "BrowserScraper",
    "DASHBOARD_HTML_PATH",
    "DATA_DIR",
    "DOCS_DASHBOARD_HTML_PATH",
    "DOCS_TERMINAL_DASHBOARD_HTML_PATH",
    "DatabaseManager",
    "ScraperType",
    "SourceKind",
    "StaticScraper",
    "TERMINAL_DASHBOARD_HTML_PATH",
    "_cli",
    "_create_scraper",
    "_generate_pipeline_dashboards",
    "_persist_collection",
    "_publish_collection",
    "app",
    "clean_products",
    "generate_dashboard",
    "generate_terminal_dashboard",
]

if __name__ == "__main__":
    app()
