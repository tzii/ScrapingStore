"""
ScrapingStore CLI
=================
Main entry point for the application.
"""

from enum import Enum
import json
from uuid import uuid4
from typing import Any, Dict, Optional

import typer

from cleaning.data_cleaner import clean_products
from config import (
    BASE_URL,
    DATA_DIR,
    DASHBOARD_HTML_PATH,
    DOCS_DASHBOARD_HTML_PATH,
    DOCS_TERMINAL_DASHBOARD_HTML_PATH,
    TERMINAL_DASHBOARD_HTML_PATH,
)
from database import DatabaseManager, HISTORY_VERSION
from logger import get_logger, setup_logger
from scraper.base import BaseScraper
from scraper.results import ScrapeRunResult
from scraper.product_scraper import StaticScraper
from scraper.product_scraper_browser import BrowserScraper
from visualization.dashboard_generator import generate_dashboard
from visualization.terminal_dashboard_generator import generate_terminal_dashboard
from visualization.report_data import ReportSnapshot

app = typer.Typer(
    help="ScrapingStore Data Pipeline CLI",
    invoke_without_command=True,
)
logger = get_logger("main")


class ScraperType(str, Enum):
    static = "static"
    browser = "browser"


@app.callback()
def setup(ctx: typer.Context, verbose: bool = False):
    """
    Global setup (logging).
    """
    level = "DEBUG" if verbose else "INFO"
    setup_logger(level)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _create_scraper(scraper_type: ScraperType, delay: float) -> BaseScraper:
    """Create the requested scraper implementation."""
    if scraper_type == ScraperType.static:
        return StaticScraper(base_url=BASE_URL, delay=delay)
    return BrowserScraper(base_url=BASE_URL, delay=delay)


def _generate_pipeline_dashboards(
    db: DatabaseManager,
    dashboard_path: Optional[str] = None,
    terminal_path: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """Select the stored catalog once and render both views of that snapshot."""
    logger.info("Generating dashboard...")
    if run_id is None:
        products, run = db.get_catalog_snapshot()
        snapshot = ReportSnapshot.from_products(products, run=run)
    else:
        snapshot = ReportSnapshot.from_products(
            db.get_run_products(run_id),
            run=db.get_run(run_id),
            scope=f"Collection run {run_id}",
            collection_label="Selected collection",
        )
    dashboard_path = dashboard_path or str(DASHBOARD_HTML_PATH)
    terminal_path = terminal_path or str(TERMINAL_DASHBOARD_HTML_PATH)
    generate_dashboard(
        snapshot, output_path=dashboard_path, terminal_path=terminal_path
    )
    generate_terminal_dashboard(
        snapshot, output_path=terminal_path, dashboard_path=dashboard_path
    )


@app.command()
def scrape(
    scraper_type: ScraperType = typer.Option(
        ScraperType.browser,
        "--type",
        help="Type of scraper (browser for the default source)",
    ),
    pages: Optional[int] = typer.Option(10, min=1, help="Max pages to scrape"),
    all_pages: bool = typer.Option(False, "--all", help="Scrape all available pages"),
    delay: float = typer.Option(
        1.0,
        min=0.0,
        help="Delay between page batches (browser) or pages (static), in seconds",
    ),
    export: bool = typer.Option(True, help="Export to Power BI CSV after scraping"),
    dashboard: bool = typer.Option(True, help="Generate dashboard after scraping"),
    allow_partial: bool = typer.Option(
        False, help="Publish partial observations with warnings (exit code remains 2)"
    ),
    page_budget: int = typer.Option(
        200, min=1, help="Hard page budget, including --all"
    ),
    run_timeout: float = typer.Option(1800, min=1, help="Run deadline in seconds"),
):
    """
    Run the scraping pipeline: Scrape -> Clean -> DB -> Export.
    """
    max_pages = None if all_pages else pages
    db = DatabaseManager()
    scraper = None
    run = ScrapeRunResult(BASE_URL, max_pages, scraper_type.value)
    try:
        db.init_db()
        try:
            scraper = _create_scraper(scraper_type, delay)
            scraper.page_budget = page_budget
            scraper.run_timeout = run_timeout
            run = scraper.scrape(max_pages=max_pages)
        except KeyboardInterrupt:
            run = (scraper.last_run if scraper else None) or run
            run.errors.append("Collection cancelled by user")
            run.finish("cancelled")
        except Exception as exc:
            run = (scraper.last_run if scraper else None) or run
            run.errors.append(f"{type(exc).__name__}: {exc}")
            run.finish("collector_error")
        _persist_collection(db, run)
        _publish_collection(db, run, export, dashboard, allow_partial)
    finally:
        try:
            if scraper:
                scraper.close()
        finally:
            db.close()


def _publish_collection(
    db: DatabaseManager,
    run: ScrapeRunResult,
    export: bool,
    dashboard: bool,
    allow_partial: bool,
) -> None:
    typer.echo(
        f"Collection {run.status}: {len(run.pages)} pages attempted; "
        f"{run.accepted_products} products saved. Stop: {run.stop_reason}."
    )
    publish = run.status in ("complete", "empty") or (
        run.status == "partial" and allow_partial
    )
    if publish:
        if export:
            db.export_for_powerbi()
        if dashboard:
            _generate_pipeline_dashboards(db)
    elif export or dashboard:
        typer.echo(
            "Automatic publication skipped. Partial results require --allow-partial."
        )
    if run.status == "partial":
        raise typer.Exit(code=2)
    if run.status == "cancelled":
        raise typer.Exit(code=130)
    if run.status == "failed":
        raise typer.Exit(code=1)


def _persist_collection(db: DatabaseManager, run: ScrapeRunResult) -> None:
    products = clean_products(run.products, warnings=run.errors)
    for product in products:
        product.last_run_id = run.run_id
    persistence_error = None
    try:
        run.accepted_products = len(products)
        manifest = {**run.manifest(), "history_version": HISTORY_VERSION}
        db.save_collection(products, manifest)
    except Exception as exc:
        persistence_error = exc
        run.accepted_products = 0
        run.errors.append(f"persistence_error: {exc}")
    manifest = run.manifest()
    if persistence_error is None:
        manifest["history_version"] = HISTORY_VERSION
    destination = DATA_DIR / "runs" / f"{run.run_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest, indent=2, ensure_ascii=False)
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    except FileExistsError:
        if destination.read_text(encoding="utf-8") != serialized:
            # Keep the original evidence even when a conflicting retry is rejected.
            destination = destination.with_name(f"{run.run_id}.attempt-{uuid4()}.json")
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(serialized)
    typer.echo(f"Run manifest: {destination}")
    if persistence_error is not None:
        typer.echo("Persistence failed; see the run manifest.")
        raise typer.Exit(code=1)


@app.command()
def runs(limit: int = typer.Option(20, min=1, max=1000)):
    """List saved collections, newest first."""
    db = DatabaseManager()
    try:
        db.init_db()
        manifests = db.list_runs(limit=limit)
        if not manifests:
            typer.echo("No saved collections.")
        for run in manifests:
            typer.echo(
                f"{run['run_id']}  {run['status']}  "
                f"{run.get('finished_at') or run['started_at']}  "
                f"{run.get('products_accepted', 0)} products  "
                f"{run.get('scope', {}).get('description', 'Scope not recorded')}  "
                f"Stop: {run.get('stop_reason', 'Not recorded')}"
            )
    finally:
        db.close()


@app.command("inspect-run")
def inspect_run(
    run_id: str,
    products: bool = typer.Option(
        False, "--products", help="Include the saved product observations."
    ),
):
    """Print a saved collection's page outcomes and evidence as JSON."""
    db = DatabaseManager()
    try:
        db.init_db()
        manifest = db.get_run(run_id)
        if manifest is None:
            raise ValueError(f"Collection run not found: {run_id}")
        payload: Dict[str, Any] = {"run": manifest}
        if products:
            payload["products"] = [
                product.model_dump(mode="json")
                for product in db.get_run_products(run_id)
            ]
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def export():
    """
    Export existing database data to Power BI CSV.
    """
    db = DatabaseManager()
    try:
        db.init_db()
        db.export_for_powerbi()
    finally:
        db.close()


@app.command()
def generate_report(
    docs: bool = typer.Option(
        False,
        "--docs",
        help="Write GitHub Pages files to docs/ instead of data/.",
    ),
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Render the observations saved by this collection."
    ),
):
    """
    Generate the HTML dashboard from existing data.
    """
    db = DatabaseManager()
    try:
        db.init_db()
        dashboard_path = str(DOCS_DASHBOARD_HTML_PATH) if docs else None
        terminal_path = str(DOCS_TERMINAL_DASHBOARD_HTML_PATH) if docs else None

        _generate_pipeline_dashboards(db, dashboard_path, terminal_path, run_id)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


if __name__ == "__main__":
    app()
