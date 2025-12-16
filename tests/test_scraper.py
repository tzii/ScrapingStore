import pytest
from unittest.mock import Mock, patch
from scraper.product_scraper import StaticScraper
from models import Product

@pytest.fixture
def mock_response():
    mock = Mock()
    mock.status_code = 200
    mock.content = """
    <html>
        <body>
            <div class="product-card">
                <h4>Test Product</h4>
                <img src="img.jpg">
                99.99 € In Stock
            </div>
        </body>
    </html>
    """.encode('utf-8')
    return mock

@patch('requests.Session.get')
def test_static_scraper_success(mock_get, mock_response):
    mock_get.return_value = mock_response
    
    scraper = StaticScraper(base_url="http://test.com")
    products = scraper.scrape(max_pages=1)
    
    assert len(products) == 1
    assert products[0].name == "Test Product"
    assert products[0].source_url == "http://test.com"

@patch('requests.Session.get')
def test_static_scraper_empty_page(mock_get):
    mock = Mock()
    mock.status_code = 200
    mock.content = b"<html></html>"
    mock_get.return_value = mock
    
    scraper = StaticScraper(base_url="http://test.com")
    products = scraper.scrape(max_pages=1)
    
    assert len(products) == 0
