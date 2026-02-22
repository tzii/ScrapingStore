"""
Tests for the data cleaning pipeline.
"""

import pytest
from models import Product
from cleaning.data_cleaner import clean_products


def test_clean_preserves_valid_data():
    """Test that already-valid data passes through unchanged."""
    p = Product(
        source_url="http://test.com",
        name="Test Product",
        price=59.99,
        availability="In Stock",
    )
    cleaned = clean_products([p])
    assert len(cleaned) == 1
    assert cleaned[0].price == 59.99
    assert cleaned[0].availability == "In Stock"
    assert cleaned[0].name == "Test Product"


def test_clean_normalizes_availability_in_stock():
    """Test availability normalization for in-stock items."""
    p = Product(
        source_url="http://test.com",
        name="Test",
        availability="In Stock",
    )
    cleaned = clean_products([p])
    assert cleaned[0].availability == "In Stock"


def test_clean_normalizes_availability_out_of_stock():
    """Test availability normalization for out-of-stock items."""
    p = Product(
        source_url="http://test.com",
        name="Test",
        availability="Out of Stock",
    )
    cleaned = clean_products([p])
    assert cleaned[0].availability == "Out of Stock"


def test_clean_availability_unknown_fallback():
    """Test that unrecognized availability becomes Unknown."""
    p = Product(
        source_url="http://test.com",
        name="Test",
        availability="Random String",
    )
    cleaned = clean_products([p])
    assert cleaned[0].availability == "Unknown"


def test_clean_deduplication():
    """Test removing duplicate products by name."""
    p1 = Product(source_url="http://test.com/1", name="Duplicate", price=10.0)
    p2 = Product(source_url="http://test.com/2", name="Duplicate", price=20.0)
    cleaned = clean_products([p1, p2])
    assert len(cleaned) == 1
    assert cleaned[0].price == 10.0  # keeps first


def test_clean_strips_name_whitespace():
    """Test that product names are stripped of whitespace."""
    p = Product(
        source_url="http://test.com",
        name="  Whitespace Name  ",
        price=10.0,
    )
    cleaned = clean_products([p])
    assert cleaned[0].name == "Whitespace Name"


def test_clean_empty_list():
    """Test that cleaning an empty list returns an empty list."""
    result = clean_products([])
    assert result == []


def test_clean_multiple_products(sample_products):
    """Test cleaning a batch of multiple products."""
    cleaned = clean_products(sample_products)
    assert len(cleaned) == 3
    assert all(p.availability in ("In Stock", "Out of Stock", "Unknown") for p in cleaned)


def test_clean_handles_zero_price():
    """Test that zero prices are preserved (not treated as errors)."""
    p = Product(source_url="http://test.com", name="Free Item", price=0.0)
    cleaned = clean_products([p])
    assert cleaned[0].price == 0.0
