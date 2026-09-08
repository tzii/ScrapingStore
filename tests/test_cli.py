"""
Tests for the CLI commands.
"""

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from config import (
    BASE_URL,
    DASHBOARD_HTML_PATH,
    TERMINAL_DASHBOARD_HTML_PATH,
    DOCS_DASHBOARD_HTML_PATH,
    DOCS_TERMINAL_DASHBOARD_HTML_PATH,
)
from main import app
from scraper.results import PageResult, ScrapeRunResult

runner = CliRunner()


def test_no_args_shows_help():
    """Running the CLI without a command should not start a scrape."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "scrape" in result.stdout


@patch("main.DatabaseManager")
@patch("main.BrowserScraper")
@patch("main.clean_products")
@patch("main.generate_dashboard")
@patch("main.generate_terminal_dashboard")
def test_scrape_command_default(
    mock_terminal, mock_dashboard, mock_clean, mock_scraper_cls, mock_db_cls
):
    """Test the scrape command runs with defaults."""
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = ScrapeRunResult(
        BASE_URL,
        1,
        "browser",
        pages=[PageResult(1, BASE_URL, status="empty", source_end=True)],
    ).finish("source_end")
    mock_scraper_cls.return_value = mock_scraper

    mock_clean.return_value = []

    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["scrape", "--pages", "1", "--no-dashboard"])
    assert result.exit_code == 0
    mock_scraper_cls.assert_called_once_with(base_url=BASE_URL, delay=1.0)
    mock_scraper.scrape.assert_called_once_with(max_pages=1)


@pytest.mark.parametrize("scraper_type", ["static", "browser"])
def test_explicit_scraper_selection(scraper_type):
    with (
        patch("main.DatabaseManager"),
        patch("main.StaticScraper") as static,
        patch("main.BrowserScraper") as browser,
    ):
        result_data = ScrapeRunResult(
            BASE_URL,
            2,
            scraper_type,
            pages=[PageResult(1, BASE_URL, status="empty", source_end=True)],
        ).finish("source_end")
        static.return_value.scrape.return_value = result_data
        browser.return_value.scrape.return_value = result_data
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
        assert result.exit_code == 0
        selected, other = (
            (static, browser) if scraper_type == "static" else (browser, static)
        )
        selected.return_value.scrape.assert_called_once_with(max_pages=2)
        other.assert_not_called()


@patch("main.DatabaseManager")
def test_export_command(mock_db_cls):
    """Test the export command calls export_for_powerbi."""
    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["export"])
    assert result.exit_code == 0
    mock_db.init_db.assert_called_once()
    mock_db.export_for_powerbi.assert_called_once()


@patch("main.generate_terminal_dashboard")
@patch("main.generate_dashboard")
@patch("main.DatabaseManager")
def test_generate_report_command(mock_db_cls, mock_dashboard, mock_terminal):
    """Test the generate-report command."""
    mock_db = MagicMock()
    mock_db.get_catalog_snapshot.return_value = ([], None)
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["generate-report"])
    assert result.exit_code == 0
    mock_db.init_db.assert_called_once()
    mock_db.get_catalog_snapshot.assert_called_once_with()
    snapshot = mock_dashboard.call_args.args[0]
    assert snapshot.context["products"] == []
    mock_dashboard.assert_called_once_with(
        snapshot,
        output_path=str(DASHBOARD_HTML_PATH),
        terminal_path=str(TERMINAL_DASHBOARD_HTML_PATH),
    )
    mock_terminal.assert_called_once_with(
        snapshot,
        output_path=str(TERMINAL_DASHBOARD_HTML_PATH),
        dashboard_path=str(DASHBOARD_HTML_PATH),
    )


@patch("main.generate_terminal_dashboard")
@patch("main.generate_dashboard")
@patch("main.DatabaseManager")
def test_generate_report_docs_paths(mock_db_cls, mock_dashboard, mock_terminal):
    """The docs flag should target the GitHub Pages files."""
    mock_db = MagicMock()
    mock_db.get_catalog_snapshot.return_value = ([], None)
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["generate-report", "--docs"])

    assert result.exit_code == 0
    assert Path(mock_dashboard.call_args.kwargs["output_path"]) == (
        DOCS_DASHBOARD_HTML_PATH
    )
    assert Path(mock_terminal.call_args.kwargs["output_path"]) == (
        DOCS_TERMINAL_DASHBOARD_HTML_PATH
    )
