"""
Tests for the dashboard generator.
"""

from visualization.dashboard_generator import generate_dashboard


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
    """No file is written when the database has no products."""
    output = tmp_path / "dashboard.html"

    generate_dashboard(db_manager, output_path=str(output))

    assert not output.exists()
