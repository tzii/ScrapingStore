"""
Tests for the CLI commands.
"""

from unittest.mock import patch, MagicMock
from pathlib import Path

from typer.testing import CliRunner

from config import DOCS_DASHBOARD_HTML_PATH, DOCS_TERMINAL_DASHBOARD_HTML_PATH
from main import app

runner = CliRunner()


def test_no_args_shows_help():
    """Running the CLI without a command should not start a scrape."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "scrape" in result.stdout


@patch("main.DatabaseManager")
@patch("main.StaticScraper")
@patch("main.clean_products")
@patch("main.generate_dashboard")
@patch("main.generate_terminal_dashboard")
def test_scrape_command_default(
    mock_terminal, mock_dashboard, mock_clean, mock_scraper_cls, mock_db_cls
):
    """Test the scrape command runs with defaults."""
    mock_scraper = MagicMock()
    mock_scraper.scrape.return_value = []
    mock_scraper_cls.return_value = mock_scraper

    mock_clean.return_value = []

    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["scrape", "--pages", "1", "--no-dashboard"])
    assert result.exit_code == 0


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
    mock_db.get_all_products.return_value = []
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["generate-report"])
    assert result.exit_code == 0
    mock_db.init_db.assert_called_once()
    mock_dashboard.assert_called_once_with(mock_db, output_path=None)
    mock_terminal.assert_called_once_with([], output_path=None)


@patch("main.generate_terminal_dashboard")
@patch("main.generate_dashboard")
@patch("main.DatabaseManager")
def test_generate_report_docs_paths(mock_db_cls, mock_dashboard, mock_terminal):
    """The docs flag should target the GitHub Pages files."""
    mock_db = MagicMock()
    mock_db.get_all_products.return_value = []
    mock_db_cls.return_value = mock_db

    result = runner.invoke(app, ["generate-report", "--docs"])

    assert result.exit_code == 0
    assert Path(mock_dashboard.call_args.kwargs["output_path"]) == (
        DOCS_DASHBOARD_HTML_PATH
    )
    assert Path(mock_terminal.call_args.kwargs["output_path"]) == (
        DOCS_TERMINAL_DASHBOARD_HTML_PATH
    )
