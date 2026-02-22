"""
Tests for the CLI commands.
"""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from main import app

runner = CliRunner()


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
    mock_dashboard.assert_called_once()
