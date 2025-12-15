import pytest
from models import Product
from cleaning.data_cleaner import clean_products

def test_clean_price_normal():
    """Test cleaning a normal Euro price string."""
    p = Product(source_url="http://test.com", name="Test", availability="88,99 €")
    cleaned = clean_products([p])
    assert cleaned[0].price == 88.99

def test_clean_price_dot():
    """Test cleaning a Euro price with dot."""
    p = Product(source_url="http://test.com", name="Test", availability="88.99 €")
    cleaned = clean_products([p])
    assert cleaned[0].price == 88.99

def test_availability_in_stock():
    """Test availability status extraction."""
    p = Product(source_url="http://test.com", name="Test", availability="In Stock")
    cleaned = clean_products([p])
    assert cleaned[0].availability == "In Stock"

def test_availability_bad_string():
    """Test availability fallback."""
    p = Product(source_url="http://test.com", name="Test", availability="Random String")
    cleaned = clean_products([p])
    assert cleaned[0].availability == "Unknown"

def test_deduplication():
    """Test removing duplicate products by name."""
    p1 = Product(source_url="http://test.com/1", name="Duplicate", availability="10 €")
    p2 = Product(source_url="http://test.com/2", name="Duplicate", availability="10 €")
    cleaned = clean_products([p1, p2])
    assert len(cleaned) == 1
