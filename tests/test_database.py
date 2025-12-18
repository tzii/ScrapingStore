import pytest
from sqlmodel import Session, SQLModel, create_engine
from database import DatabaseManager
from models import Product


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="db_manager")
def db_manager_fixture(tmp_path):
    # Create DB manager with a temp file or memory
    # Since DatabaseManager takes a URL, we can use in-memory
    db = DatabaseManager("sqlite:///")
    db.init_db()
    return db


def test_save_and_get_products(db_manager):
    products = [
        Product(name="Test1", source_url="http://test.com/1", price=10.0),
        Product(name="Test2", source_url="http://test.com/2", price=20.0),
    ]

    db_manager.save_products(products)

    saved = db_manager.get_all_products()
    assert len(saved) == 2
    assert saved[0].name == "Test1"


def test_upsert_products(db_manager):
    p1 = Product(name="Old Name", source_url="http://test.com/1", price=10.0)
    db_manager.save_products([p1])

    p2 = Product(name="Old Name", source_url="http://test.com/1", price=50.0)
    db_manager.save_products([p2])

    saved = db_manager.get_all_products()
    assert len(saved) == 1
    assert saved[0].price == 50.0
    assert saved[0].name == "Old Name"


def test_export_powerbi(db_manager, tmp_path):
    p1 = Product(name="P1", source_url="u1", price=10)
    db_manager.save_products([p1])

    output_file = tmp_path / "export.csv"
    db_manager.export_for_powerbi(str(output_file))

    assert output_file.exists()
    content = output_file.read_text("utf-8-sig")
    assert "P1" in content
