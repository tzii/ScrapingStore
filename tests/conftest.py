"""
Shared test fixtures for ScrapingStore test suite.
"""

import pytest

from database import DatabaseManager
from models import Product

SAMPLE_HTML = """
<html>
    <body>
        <div class="product-card">
            <h4>Zelda: Breath of the Wild</h4>
            <img src="zelda.jpg">
            <div class="price-wrapper">59,99 €</div><span class="availability">In Stock</span>
        </div>
        <div class="product-card">
            <h4>Mario Kart 8 Deluxe</h4>
            <img src="mario.jpg">
            <div class="price-wrapper">49,99 €</div><span class="availability">In Stock</span>
        </div>
        <div class="product-card">
            <h4>Metal Gear Solid V</h4>
            <img src="mgs.jpg">
            <div class="price-wrapper">29,99 €</div><span class="availability">Out of Stock</span>
        </div>
    </body>
</html>
"""

EMPTY_HTML = '<html><body><p data-empty="true">No products</p></body></html>'


@pytest.fixture
def sample_html_bytes() -> bytes:
    return SAMPLE_HTML.encode("utf-8")


@pytest.fixture
def empty_html_bytes() -> bytes:
    return EMPTY_HTML.encode("utf-8")


@pytest.fixture
def db_manager():
    """In-memory database manager for testing."""
    db = DatabaseManager("sqlite://")
    db.init_db()
    yield db
    db.close()


@pytest.fixture
def sample_products() -> list[Product]:
    """A list of sample Product objects for testing."""
    return [
        Product(
            name="Zelda: Breath of the Wild",
            source_id="1",
            source_url="http://test.com",
            price=59.99,
            availability="In Stock",
            image_url="zelda.jpg",
        ),
        Product(
            name="Mario Kart 8 Deluxe",
            source_id="2",
            source_url="http://test.com",
            price=49.99,
            availability="In Stock",
            image_url="mario.jpg",
        ),
        Product(
            name="Metal Gear Solid V",
            source_id="3",
            source_url="http://test.com",
            price=29.99,
            availability="Out of Stock",
            image_url="mgs.jpg",
        ),
    ]


def pytest_addoption(parser):
    parser.addoption(
        "--run-browser",
        action="store_true",
        default=False,
        help="Run dashboard browser tests (requires npm ci and Playwright Chromium).",
    )
