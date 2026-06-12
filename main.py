"""
ScrapingStore CLI
=================
Main entry point for the application.
"""

from enum import Enum
import time
from typing import Optional

import typer

from cleaning.data_cleaner import clean_products
from config import (
    BASE_URL,
    DOCS_DASHBOARD_HTML_PATH,
    DOCS_TERMINAL_DASHBOARD_HTML_PATH,
)
from database import DatabaseManager
from logger import get_logger, setup_logger
from models import Product
from scraper.base import BaseScraper
from scraper.product_scraper import StaticScraper
from scraper.product_scraper_browser import BrowserScraper
from visualization.dashboard_generator import generate_dashboard
from visualization.terminal_dashboard_generator import generate_terminal_dashboard

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
    db: DatabaseManager, cleaned_products: list[Product]
) -> None:
    """Generate both dashboards, falling back to existing database data."""
    logger.info("Generating dashboard...")
    generate_dashboard(db)
    products = cleaned_products or db.get_all_products()
    generate_terminal_dashboard(products)


@app.command()
def scrape(
    scraper_type: ScraperType = typer.Option(
        ScraperType.static, "--type", help="Type of scraper to use"
    ),
    pages: Optional[int] = typer.Option(10, min=1, help="Max pages to scrape"),
    all_pages: bool = typer.Option(False, "--all", help="Scrape all available pages"),
    delay: float = typer.Option(1.0, min=0.0, help="Delay between requests (seconds)"),
    export: bool = typer.Option(True, help="Export to Power BI CSV after scraping"),
    dashboard: bool = typer.Option(True, help="Generate dashboard after scraping"),
):
    """
    Run the scraping pipeline: Scrape -> Clean -> DB -> Export.
    """
    start_time = time.time()

    max_pages = None if all_pages else pages
    logger.info(
        f"Starting pipeline using {scraper_type.value} scraper"
        f" ({'all pages' if all_pages else f'{max_pages} pages'})..."
    )

    # 1. Initialize DB
    db = DatabaseManager()
    db.init_db()

    # 2. Select Scraper
    scraper = _create_scraper(scraper_type, delay)

    # 3. Scrape
    try:
        raw_products = scraper.scrape(max_pages=max_pages)
        logger.info(f"Scraped {len(raw_products)} raw items.")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise typer.Exit(code=1)

    # 4. Clean
    cleaned_products = clean_products(raw_products)

    # 5. Save to DB
    if cleaned_products:
        db.save_products(cleaned_products)
    else:
        logger.warning("No products to save.")

    # 6. Export
    if export:
        db.export_for_powerbi()

    # 7. Dashboard
    if dashboard:
        _generate_pipeline_dashboards(db, cleaned_products)

    duration = time.time() - start_time
    logger.info(f"Pipeline completed in {duration:.2f} seconds.")


@app.command()
def export():
    """
    Export existing database data to Power BI CSV.
    """
    db = DatabaseManager()
    db.init_db()
    db.export_for_powerbi()


@app.command()
def generate_report(
    docs: bool = typer.Option(
        False,
        "--docs",
        help="Write GitHub Pages files to docs/ instead of data/.",
    ),
):
    """
    Generate the HTML dashboard from existing data.
    """
    db = DatabaseManager()
    db.init_db()
    dashboard_path = str(DOCS_DASHBOARD_HTML_PATH) if docs else None
    terminal_path = str(DOCS_TERMINAL_DASHBOARD_HTML_PATH) if docs else None

    generate_dashboard(db, output_path=dashboard_path)
    generate_terminal_dashboard(db.get_all_products(), output_path=terminal_path)


if __name__ == "__main__":
    app()
