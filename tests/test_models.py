"""
Tests for Product model validation.
"""

import pytest
from models import Product


def test_product_creation():
    """Test basic product creation."""
    p = Product(name="Test", source_url="http://test.com", price=10.0)
    assert p.name == "Test"
    assert p.price == 10.0


def test_product_name_stripped():
    """Test that product name is stripped on creation."""
    p = Product(name="  Test  ", source_url="http://test.com")
    assert p.name == "Test"


def test_product_empty_name_raises():
    """Test that empty name raises ValueError."""
    with pytest.raises(ValueError, match="Product name must not be empty"):
        Product(name="", source_url="http://test.com")


def test_product_whitespace_name_raises():
    """Test that whitespace-only name raises ValueError."""
    with pytest.raises(ValueError, match="Product name must not be empty"):
        Product(name="   ", source_url="http://test.com")


def test_product_negative_price_raises():
    """Test that negative price raises ValueError."""
    with pytest.raises(ValueError, match="Price must be non-negative"):
        Product(name="Test", source_url="http://test.com", price=-5.0)


def test_product_zero_price_allowed():
    """Test that zero price is allowed."""
    p = Product(name="Test", source_url="http://test.com", price=0.0)
    assert p.price == 0.0


def test_product_defaults():
    """Test default values."""
    p = Product(name="Test", source_url="http://test.com")
    assert p.price == 0.0
    assert p.currency == "EUR"
    assert p.availability == "Unknown"
    assert p.image_url is None
    assert p.category is None
    assert p.rating is None
    assert p.id is None
    assert p.scraped_at is not None
