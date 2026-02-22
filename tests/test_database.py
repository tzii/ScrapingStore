"""
Tests for the DatabaseManager module.
"""

import pytest
from database import DatabaseManager
from models import Product


def test_save_and_get_products(db_manager):
    """Test basic save and retrieve."""
    products = [
        Product(name="Test1", source_url="http://test.com/1", price=10.0),
        Product(name="Test2", source_url="http://test.com/2", price=20.0),
    ]

    db_manager.save_products(products)

    saved = db_manager.get_all_products()
    assert len(saved) == 2
    assert saved[0].name == "Test1"
    assert saved[1].name == "Test2"


def test_upsert_updates_existing(db_manager):
    """Test that saving a product with the same name updates it."""
    p1 = Product(name="Old Name", source_url="http://test.com/1", price=10.0)
    db_manager.save_products([p1])

    p2 = Product(name="Old Name", source_url="http://test.com/1", price=50.0)
    db_manager.save_products([p2])

    saved = db_manager.get_all_products()
    assert len(saved) == 1
    assert saved[0].price == 50.0


def test_get_products_df(db_manager):
    """Test retrieving products as a DataFrame."""
    products = [
        Product(name="P1", source_url="http://test.com", price=10.0),
        Product(name="P2", source_url="http://test.com", price=20.0),
    ]
    db_manager.save_products(products)

    df = db_manager.get_products_df()
    assert len(df) == 2
    assert "name" in df.columns
    assert "price" in df.columns


def test_export_powerbi(db_manager, tmp_path):
    """Test Power BI CSV export."""
    p1 = Product(name="P1", source_url="u1", price=10)
    db_manager.save_products([p1])

    output_file = tmp_path / "export.csv"
    db_manager.export_for_powerbi(str(output_file))

    assert output_file.exists()
    content = output_file.read_text("utf-8-sig")
    assert "P1" in content


def test_save_empty_list(db_manager):
    """Test that saving an empty list is a no-op."""
    db_manager.save_products([])
    assert db_manager.get_all_products() == []


def test_get_products_df_empty(db_manager):
    """Test DataFrame from empty DB."""
    df = db_manager.get_products_df()
    assert df.empty
