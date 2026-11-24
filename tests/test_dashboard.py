"""Tests for the offline HTML report generator."""

import pytest

from scrapingstore.ledger.models import Product
from scrapingstore.report.generator import generate_dashboard
from visualization.dashboard_generator import generate_dashboard as legacy_generate_dashboard
from visualization.terminal_dashboard_generator import generate_terminal_dashboard


def test_generate_dashboard_creates_file(tmp_path, db_manager, sample_products):
    """The report embeds the timeline and the compact columnar catalog."""
    db_manager.save_products(sample_products)
    output = tmp_path / "dashboard.html"

    result = generate_dashboard(db_manager, output_path=str(output))

    assert result == str(output)
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "ScrapingStore" in html
    assert "Zelda: Breath of the Wild" in html
    assert 'id="timeline-data"' in html
    assert 'id="columnar-data"' in html
    assert 'id="smells-data"' in html


def test_generate_dashboard_empty_db(tmp_path, db_manager):
    """An empty database produces a report that says so without JavaScript."""
    output = tmp_path / "dashboard.html"

    result = generate_dashboard(db_manager, output_path=str(output))

    assert result == str(output)
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "No data yet." in html
    assert '<main id="report" hidden>' in html
    assert '"total": 0' in html


def test_generate_dashboard_escapes_script_terminators(tmp_path, db_manager):
    """Scraped values must not be able to break out of JSON script tags."""
    malicious_name = "</script><script>window.pwned=true</script>"
    db_manager.save_products(
        [Product(name=malicious_name, source_url="https://example.test", price=1)]
    )
    output = tmp_path / "dashboard.html"

    generate_dashboard(db_manager, output_path=str(output))

    html = output.read_text(encoding="utf-8")
    assert malicious_name not in html
    assert "\\u003c/script\\u003e" in html


def test_generate_dashboard_supports_filename_only(tmp_path, db_manager, monkeypatch):
    """A destination without a parent directory should be valid."""
    db_manager.save_products(
        [Product(name="Product", source_url="https://example.test", price=1)]
    )
    monkeypatch.chdir(tmp_path)

    result = generate_dashboard(db_manager, output_path="dashboard.html")

    assert result == "dashboard.html"
    assert (tmp_path / "dashboard.html").exists()


def test_report_is_self_contained(tmp_path, db_manager, sample_products):
    """The report loads no scripts, stylesheets or fonts from the network."""
    db_manager.save_products(sample_products)
    output = tmp_path / "dashboard.html"

    generate_dashboard(db_manager, output_path=str(output))

    html = output.read_text(encoding="utf-8")
    assert "<script src" not in html
    assert "<link" not in html
    assert "@import" not in html


def test_legacy_generators_write_the_single_report(tmp_path, db_manager, sample_products):
    """2.x import paths still work, warn, and write the standard report."""
    db_manager.save_products(sample_products)
    report = tmp_path / "dashboard.html"
    terminal = tmp_path / "dashboard_terminal.html"

    with pytest.warns(DeprecationWarning):
        legacy_generate_dashboard(db_manager, str(report), terminal_path=str(terminal))
    with pytest.warns(DeprecationWarning):
        generate_terminal_dashboard(db_manager, output_path=str(terminal))

    assert 'id="timeline-data"' in report.read_text(encoding="utf-8")
    assert 'id="timeline-data"' in terminal.read_text(encoding="utf-8")
