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
            59,99 € In Stock
        </div>
        <div class="product-card">
            <h4>Mario Kart 8 Deluxe</h4>
            <img src="mario.jpg">
            49,99 € In Stock
        </div>
        <div class="product-card">
            <h4>Metal Gear Solid V</h4>
            <img src="mgs.jpg">
            29,99 € Out of Stock
        </div>
    </body>
</html>
"""

EMPTY_HTML = "<html><body></body></html>"


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
            source_url="http://test.com",
            price=59.99,
            availability="In Stock",
            image_url="zelda.jpg",
        ),
        Product(
            name="Mario Kart 8 Deluxe",
            source_url="http://test.com",
            price=49.99,
            availability="In Stock",
            image_url="mario.jpg",
        ),
        Product(
            name="Metal Gear Solid V",
            source_url="http://test.com",
            price=29.99,
            availability="Out of Stock",
            image_url="mgs.jpg",
        ),
    ]
