"""
ScrapingStore CLI
=================
Main entry point for the application.
"""

import typer
from typing import Optional
from enum import Enum
import time

from models import Product
from visualization.dashboard_generator import generate_dashboard
from visualization.terminal_dashboard_generator import generate_terminal_dashboard
from config import BASE_URL
from logger import setup_logger, get_logger
from database import DatabaseManager
from scraper.product_scraper import StaticScraper
from scraper.product_scraper_browser import BrowserScraper
from cleaning.data_cleaner import clean_products
from scraper.base import BaseScraper

app = typer.Typer(help="ScrapingStore Data Pipeline CLI")
logger = get_logger("main")


class ScraperType(str, Enum):
    static = "static"
    browser = "browser"


@app.callback()
def setup(verbose: bool = False):
    """
    Global setup (logging).
    """
    level = "DEBUG" if verbose else "INFO"
    setup_logger(level)


@app.command()
def scrape(
    type: ScraperType = typer.Option(ScraperType.static, help="Type of scraper to use"),
    pages: Optional[int] = typer.Option(10, help="Max pages to scrape"),
    all: bool = typer.Option(False, "--all", help="Scrape all available pages"),
    delay: float = typer.Option(1.0, help="Delay between requests (seconds)"),
    export: bool = typer.Option(True, help="Export to Power BI CSV after scraping"),
    dashboard: bool = typer.Option(True, help="Generate dashboard after scraping"),
):
    """
    Run the scraping pipeline: Scrape -> Clean -> DB -> Export.
    """
    start_time = time.time()

    max_pages = None if all else pages
    logger.info(
        f"Starting pipeline using {type.value} scraper"
        f" ({'all pages' if all else f'{max_pages} pages'})..."
    )

    # 1. Initialize DB
    db = DatabaseManager()
    db.init_db()

    # 2. Select Scraper
    scraper: BaseScraper
    if type == ScraperType.static:
        scraper = StaticScraper(base_url=BASE_URL, delay=delay)
    else:
        scraper = BrowserScraper(base_url=BASE_URL, delay=delay)

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
        logger.info("Generating dashboard...")
        # We pass the DB manager to the dashboard generator so it can query stats
        generate_dashboard(db)
        if cleaned_products:
            generate_terminal_dashboard(cleaned_products)
        else:
            # If no new products, try to get from DB for terminal dashboard
            # Note: generate_terminal_dashboard expects a list of Product objects.
            # We might need to fetch them if cleaned_products is empty but DB has data.
            pass

    duration = time.time() - start_time
    logger.info(f"Pipeline completed in {duration:.2f} seconds.")


@app.command()
def export():
    """
    Export existing database data to Power BI CSV.
    """
    db = DatabaseManager()
    db.export_for_powerbi()


@app.command()
def generate_report():
    """
    Generate the HTML dashboard from existing data.
    """
    db = DatabaseManager()
    generate_dashboard(db)

    try:
        products = db.get_all_products()
        if products:
            generate_terminal_dashboard(products)
    except Exception as e:
        logger.warning(f"Could not generate terminal dashboard from DB: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        # Default to 'scrape' command if no args provided
        sys.argv.append("scrape")
    app()
