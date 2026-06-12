"""
Tests for the dashboard generator.
"""

from models import Product
from visualization.dashboard_generator import generate_dashboard
from visualization.terminal_dashboard_generator import generate_terminal_dashboard


def test_generate_dashboard_creates_file(tmp_path, db_manager, sample_products):
    """Dashboard HTML is rendered with product data embedded."""
    db_manager.save_products(sample_products)
    output = tmp_path / "dashboard.html"

    result = generate_dashboard(db_manager, output_path=str(output))

    assert result == str(output)
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "ScrapingStore" in html
    assert "Zelda: Breath of the Wild" in html
    # New stats are embedded for the redesigned dashboard
    assert "top-products-data" in html
    assert "availability-data" in html


def test_generate_dashboard_empty_db(tmp_path, db_manager):
    """An empty database should still produce a usable dashboard."""
    output = tmp_path / "dashboard.html"

    result = generate_dashboard(db_manager, output_path=str(output))

    assert result == str(output)
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "No data yet" in html
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


def test_generate_terminal_dashboard_escapes_script_terminators(tmp_path):
    """The terminal dashboard must use HTML-safe JSON as well."""
    malicious_name = "</script><script>window.pwned=true</script>"
    output = tmp_path / "terminal.html"
    product = Product(
        name=malicious_name,
        source_url="https://example.test",
        price=1,
    )

    result = generate_terminal_dashboard([product], output_path=str(output))

    assert result == str(output)
    html = output.read_text(encoding="utf-8")
    assert malicious_name not in html
    assert "\\u003c/script\\u003e" in html


def test_generate_terminal_dashboard_empty_state(tmp_path):
    output = tmp_path / "terminal.html"

    generate_terminal_dashboard([], output_path=str(output))

    assert output.exists()
    assert "const total = products.length" in output.read_text(encoding="utf-8")
