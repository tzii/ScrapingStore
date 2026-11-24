"""Render the single-file, offline HTML report (autoescaped, written atomically)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scrapingstore.config import get_settings
from scrapingstore.io_utils import atomic_write_text
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.ledger.models import Product
from scrapingstore.logger import get_logger
from scrapingstore.report.snapshot import ReportSnapshot

logger = get_logger(__name__)

ReportSource = Union[DatabaseManager, ReportSnapshot, List[Product]]


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(get_settings().templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        keep_trailing_newline=True,
    )


def _snapshot_from_source(
    source: ReportSource, *, include_history: bool = True, history_runs: int = 12
) -> ReportSnapshot:
    if isinstance(source, ReportSnapshot):
        return source
    if isinstance(source, DatabaseManager):
        products, run = source.get_catalog_snapshot()
        history = source.get_multi_run_history(limit=history_runs) if include_history else None
        return ReportSnapshot.from_products(products, run=run, history=history)
    return ReportSnapshot.from_products(source)


def render_report(snapshot: ReportSnapshot) -> str:
    """Render a snapshot into the self-contained report HTML."""
    # Row dicts stay out of the page; the catalog travels as the compact columnar bundle.
    context = {k: v for k, v in snapshot.context.items() if k != "products"}
    return _jinja_env().get_template("report.html").render(**context)


def generate_dashboard(
    source: ReportSource,
    output_path: Optional[str] = None,
    *,
    include_history: bool = True,
    history_runs: int = 12,
) -> str:
    """Write the HTML report for a database, snapshot or product list and return its path."""
    snapshot = _snapshot_from_source(
        source, include_history=include_history, history_runs=history_runs
    )
    destination = Path(output_path) if output_path else get_settings().dashboard_html_path
    atomic_write_text(destination, render_report(snapshot), encoding="utf-8")
    logger.info("Report saved to %s", destination)
    return str(destination)
