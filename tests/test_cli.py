"""Tests for the ScrapingStore CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from scrapingstore.cli.app import app
from scrapingstore.config import get_settings
from scrapingstore.sources.results import PageResult, ScrapeRunResult

runner = CliRunner()


def test_no_args_shows_help():
    """Running the CLI without a command should not start a scrape."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "scrape" in result.stdout
    assert "demo" in result.stdout


@patch("scrapingstore.cli.app.DatabaseManager")
@patch("scrapingstore.cli.app.AutoScraper")
@patch("scrapingstore.cli.app.clean_products")
@patch("scrapingstore.cli.app.generate_dashboard")
def test_scrape_command_default_uses_auto(
    mock_dashboard, mock_clean, mock_scraper_cls, mock_db_cls
):
    """Default scrape uses AutoScraper (HTTP first with browser fallback)."""
    settings = get_settings()
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = ScrapeRunResult(
        settings.base_url,
        1,
        "static",
        pages=[PageResult(1, settings.base_url, status="empty", source_end=True)],
    ).finish("source_end")
    mock_scraper_cls.return_value = mock_scraper
    mock_clean.return_value = []
    mock_db = MagicMock()
    mock_db.list_runs.return_value = []
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["scrape", "--pages", "1", "--no-dashboard"])
    assert result.exit_code == 0, result.output
    assert mock_scraper_cls.call_count == 1
    assert mock_scraper_cls.call_args.kwargs["base_url"] == settings.base_url
    assert mock_scraper_cls.call_args.kwargs["delay"] == 1.0
    mock_scraper.scrape.assert_called_once_with(max_pages=1)


@pytest.mark.parametrize("scraper_type", ["static", "browser", "auto"])
def test_explicit_scraper_selection(scraper_type):
    settings = get_settings()
    with (
        patch("scrapingstore.cli.app.DatabaseManager") as db_cls,
        patch("scrapingstore.cli.app.StaticScraper") as static,
        patch("scrapingstore.cli.app.BrowserScraper") as browser,
        patch("scrapingstore.cli.app.AutoScraper") as auto,
    ):
        db_cls.return_value.list_runs.return_value = []
        result_data = ScrapeRunResult(
            settings.base_url,
            2,
            scraper_type,
            pages=[PageResult(1, settings.base_url, status="empty", source_end=True)],
        ).finish("source_end")
        static.return_value.scrape.return_value = result_data
        browser.return_value.scrape.return_value = result_data
        auto.return_value.scrape.return_value = result_data
        result = runner.invoke(
            app,
            [
                "scrape",
                "--type",
                scraper_type,
                "--pages",
                "2",
                "--no-dashboard",
                "--no-export",
            ],
        )
        assert result.exit_code == 0, result.output
        mapping = {"static": static, "browser": browser, "auto": auto}
        mapping[scraper_type].return_value.scrape.assert_called_once_with(max_pages=2)
        for key, mock_cls in mapping.items():
            if key != scraper_type:
                mock_cls.assert_not_called()


@patch("scrapingstore.cli.app.DatabaseManager")
def test_export_command(mock_db_cls):
    """Test the export command calls export_for_powerbi."""
    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["export"])
    assert result.exit_code == 0
    mock_db.init_db.assert_called_once()
    mock_db.export_for_powerbi.assert_called_once()


@patch("scrapingstore.cli.app.generate_dashboard")
@patch("scrapingstore.cli.app.DatabaseManager")
def test_generate_report_command(mock_db_cls, mock_dashboard):
    """Test the generate-report command."""
    settings = get_settings()
    mock_db = MagicMock()
    mock_db.get_catalog_snapshot.return_value = ([], None)
    mock_db.get_multi_run_history.return_value = []
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["generate-report"])
    assert result.exit_code == 0
    mock_db.init_db.assert_called_once()
    mock_db.get_catalog_snapshot.assert_called_once_with()
    snapshot = mock_dashboard.call_args.args[0]
    assert snapshot.context["products"] == []
    mock_dashboard.assert_called_once_with(
        snapshot, output_path=str(settings.dashboard_html_path)
    )


@patch("scrapingstore.cli.app.generate_dashboard")
@patch("scrapingstore.cli.app.DatabaseManager")
def test_generate_report_docs_paths(mock_db_cls, mock_dashboard):
    """The docs flag should target the GitHub Pages file."""
    settings = get_settings()
    mock_db = MagicMock()
    mock_db.get_catalog_snapshot.return_value = ([], None)
    mock_db.get_multi_run_history.return_value = []
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["generate-report", "--docs"])

    assert result.exit_code == 0
    assert Path(mock_dashboard.call_args.kwargs["output_path"]) == (
        settings.docs_dashboard_html_path
    )
