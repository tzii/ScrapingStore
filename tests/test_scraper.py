"""
Tests for the StaticScraper module.
"""

import pytest
from unittest.mock import Mock, patch
from scraper.product_scraper import StaticScraper
from models import Product


@pytest.fixture
def scraper():
    return StaticScraper(base_url="http://test.com", delay=0)


@pytest.fixture
def mock_response(sample_html_bytes):
    mock = Mock()
    mock.status_code = 200
    mock.content = sample_html_bytes
    mock.raise_for_status = Mock()
    return mock


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_parses_products(mock_session, mock_response):
    """Test that scraper correctly parses multiple products from HTML."""
    session = Mock()
    session.get.return_value = mock_response
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=1)

    assert len(products) == 3
    assert products[0].name == "Zelda: Breath of the Wild"
    assert products[1].name == "Mario Kart 8 Deluxe"
    assert products[2].name == "Metal Gear Solid V"


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_extracts_prices(mock_session, mock_response):
    """Test that scraper extracts prices correctly from card text."""
    session = Mock()
    session.get.return_value = mock_response
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=1)

    assert products[0].price == 59.99
    assert products[1].price == 49.99
    assert products[2].price == 29.99


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_extracts_availability(mock_session, mock_response):
    """Test that scraper extracts availability status correctly."""
    session = Mock()
    session.get.return_value = mock_response
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=1)

    assert products[0].availability == "In Stock"
    assert products[2].availability == "Out of Stock"


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_extracts_images(mock_session, mock_response):
    """Test that scraper extracts image URLs."""
    session = Mock()
    session.get.return_value = mock_response
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=1)

    assert products[0].image_url == "zelda.jpg"


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_empty_page(mock_session, empty_html_bytes):
    """Test scraper handles empty pages gracefully."""
    session = Mock()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.content = empty_html_bytes
    mock_resp.raise_for_status = Mock()
    session.get.return_value = mock_resp
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=1)

    assert len(products) == 0


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_stops_after_consecutive_empty(mock_session):
    """Test scraper stops after 3 consecutive empty pages."""
    session = Mock()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.content = b"<html></html>"
    mock_resp.raise_for_status = Mock()
    session.get.return_value = mock_resp
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=10)

    assert len(products) == 0
    # Should have been called 3 times before stopping
    assert session.get.call_count == 3


@patch("scraper.product_scraper.StaticScraper._create_session")
def test_static_scraper_retry_on_error(mock_session):
    """Test scraper handles request errors without crashing."""
    session = Mock()
    session.get.side_effect = Exception("Connection error")
    mock_session.return_value = session

    scraper = StaticScraper(base_url="http://test.com", delay=0)
    products = scraper.scrape(max_pages=1)

    assert len(products) == 0


def test_extract_price_euro_comma():
    """Test price extraction with European comma format."""
    from bs4 import BeautifulSoup

    html = '<div class="product-card"><h4>Test</h4>88,99 €</div>'
    card = BeautifulSoup(html, "html.parser").find("div")
    assert StaticScraper._extract_price(card) == 88.99


def test_extract_price_euro_dot():
    """Test price extraction with dot format."""
    from bs4 import BeautifulSoup

    html = '<div class="product-card"><h4>Test</h4>88.99 €</div>'
    card = BeautifulSoup(html, "html.parser").find("div")
    assert StaticScraper._extract_price(card) == 88.99


def test_extract_price_missing():
    """Test price extraction when no price is present."""
    from bs4 import BeautifulSoup

    html = '<div class="product-card"><h4>Test</h4>No price here</div>'
    card = BeautifulSoup(html, "html.parser").find("div")
    assert StaticScraper._extract_price(card) == 0.0


def test_extract_availability_in_stock():
    from bs4 import BeautifulSoup

    html = '<div class="product-card"><h4>Test</h4>In Stock</div>'
    card = BeautifulSoup(html, "html.parser").find("div")
    assert StaticScraper._extract_availability(card) == "In Stock"


def test_extract_availability_out_of_stock():
    from bs4 import BeautifulSoup

    html = '<div class="product-card"><h4>Test</h4>Out of Stock</div>'
    card = BeautifulSoup(html, "html.parser").find("div")
    assert StaticScraper._extract_availability(card) == "Out of Stock"


def test_extract_availability_unknown():
    from bs4 import BeautifulSoup

    html = '<div class="product-card"><h4>Test</h4>Something else</div>'
    card = BeautifulSoup(html, "html.parser").find("div")
    assert StaticScraper._extract_availability(card) == "Unknown"
