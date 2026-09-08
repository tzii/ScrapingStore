"""Behavioral regressions for uncertainty, identity, migration and publication."""

import json
import sqlite3
from datetime import timezone
from contextlib import closing
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import inspect
from typer.testing import CliRunner

from cleaning.data_cleaner import clean_products
from database import DatabaseManager
from main import app
from models import Product
from scraper.parsing import parse_page, parse_price, availability_signal
from scraper.product_scraper import StaticScraper
from scraper.results import PageResult, ScrapeRunResult
from visualization.report_data import ReportSnapshot


def card_html(identity="1", price="59,99 €", name="A product", availability="In Stock"):
    price_html = (
        f'<div class="price-wrapper">{price}</div>' if price is not None else ""
    )
    return (
        f'<div class="product-card"><a class="card-header" href="/products/{identity}">'
        f'<h4>{name}</h4></a>{price_html}<span class="availability">{availability}</span></div>'
    )


@pytest.mark.parametrize(
    "raw, expected, status",
    [
        ("59.99 €", 59.99, "known"),
        ("59,99 €", 59.99, "known"),
        ("1.299,99 €", 1299.99, "known"),
        ("1,299.99 €", 1299.99, "known"),
        ("1 299,99 €", 1299.99, "known"),
        ("1\u202f299,99 €", 1299.99, "known"),
        ("€ 59.99", 59.99, "known"),
        ("0.00 €", 0, "known"),
        (None, None, "missing"),
        ("", None, "missing"),
        ("-9.99 €", None, "invalid"),
        ("1.299 €", None, "unsupported"),
        ("Was 99.99 € Now 79.99 €", None, "ambiguous"),
        ("USD 10.00", None, "unsupported"),
        ("12,3456 €", None, "unsupported"),
    ],
)
def test_price_contract(raw, expected, status):
    result = parse_price(raw)
    assert result.value == expected
    assert result.status == status
    assert result.raw == raw


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Not in stock", "Out of Stock"),
        ("Currently unavailable. Add to basket", "Unknown"),
        ("In stock and out of stock", "Unknown"),
        ("In Stock", "In Stock"),
    ],
)
def test_availability_conflicts(raw, expected):
    assert availability_signal(raw)[0] == expected


def test_dedicated_signals_ignore_description_and_previous_price():
    html = card_html(price=None, availability="Out of Stock")
    html = html.replace("</h4>", "</h4><p>99.99 € In Stock in the description</p>")
    html = html.replace(
        '<span class="availability">',
        '<s class="old-price">89.99 €</s><span class="current-price">49.99 €</span><span class="availability">',
    )
    result = parse_page(html, "https://source.test/products", 1)
    product = result.products[0]
    assert product.price == 49.99
    assert product.availability == "Out of Stock"
    assert product.source_id == "1"
    assert product.product_url == "https://source.test/products/1"


def test_no_dedicated_price_is_missing_not_zero():
    product = parse_page(
        card_html(price=None), "https://source.test/products", 1
    ).products[0]
    assert product.price is None
    assert product.price_status == "missing"
    assert clean_products([product])[0].price is None


def test_same_name_distinct_ids_and_rename(db_manager):
    products = [
        Product(
            name="Same title",
            price=10,
            source_id=str(i),
            source_url="https://source.test/list",
        )
        for i in (1, 2)
    ]
    db_manager.save_products(clean_products(products))
    db_manager.save_products(
        [
            Product(
                name="Renamed",
                price=0,
                source_id="1",
                source_url="https://source.test/list?page=2",
            )
        ]
    )
    rows = db_manager.get_all_products()
    assert len(rows) == 2
    assert {p.name for p in rows} == {"Same title", "Renamed"}
    assert next(p for p in rows if p.source_id == "1").price == 0
    assert any(
        index["unique"] for index in inspect(db_manager.engine).get_indexes("product")
    )


def test_weak_identity_collisions_preserved_and_strong_conflicts_reported():
    weak = [Product(name="Same", source_url="https://source.test") for _ in range(2)]
    assert len(clean_products(weak)) == 2
    strong = [
        Product(
            name="Same", source_id="1", price=price, source_url="https://source.test"
        )
        for price in (10, 20)
    ]
    warnings = []
    assert len(clean_products(strong, warnings)) == 1
    assert "Conflicting observations" in warnings[0]


def test_null_and_free_prices_round_trip_and_statistics(db_manager, tmp_path):
    products = [
        Product(
            name=name, price=price, source_url="https://source.test", source_id=name
        )
        for name, price in [("unknown", None), ("free", 0), ("paid", 10)]
    ]
    db_manager.save_products(products)
    saved = db_manager.get_all_products()
    assert [p.price for p in saved] == [None, 0, 10]
    assert all(p.scraped_at.tzinfo == timezone.utc for p in saved)
    summary = ReportSnapshot.from_products(saved).context
    assert summary["statistics"]["average"] == 5
    assert summary["statistics"]["median"] == 5
    assert summary["kpi"]["missing_prices"] == 1
    assert sum(summary["chart_data"]["counts"]) == 2
    output = tmp_path / "catalog.csv"
    db_manager.export_for_powerbi(str(output))
    import csv

    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["price"] == ""
    assert float(rows[1]["price"]) == 0
    assert rows[0]["scraped_at"].endswith("Z")


def test_legacy_migration_keeps_backup_and_marks_ambiguous_zero(tmp_path):
    file = tmp_path / "legacy.db"
    with closing(sqlite3.connect(file)) as connection, connection:
        connection.execute(
            "CREATE TABLE product (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price FLOAT NOT NULL, "
            "currency TEXT NOT NULL, availability TEXT NOT NULL, image_url TEXT, "
            "source_url TEXT NOT NULL, scraped_at DATETIME NOT NULL, category TEXT, rating FLOAT)"
        )
        connection.execute("CREATE INDEX ix_product_name ON product (name)")
        for identifier, price in [(1, 0), (2, 29.99)]:
            connection.execute(
                "INSERT INTO product VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    f"Old {identifier}",
                    price,
                    "EUR",
                    "Unknown",
                    None,
                    "https://source.test/list",
                    "2026-01-01 00:00:00",
                    None,
                    None,
                ),
            )
    db = DatabaseManager(f"sqlite:///{file}")
    try:
        db.init_db()
        db.init_db()
        products = db.get_all_products()
        assert len(products) == 2
        assert (
            products[0].price is None and products[0].price_status == "legacy_unknown"
        )
        assert products[1].price == 29.99
        assert all(p.identity_kind == "legacy" for p in products)
        with closing(sqlite3.connect(file)) as connection, connection:
            assert (
                connection.execute(
                    "SELECT price FROM product_legacy_v1 WHERE id=1"
                ).fetchone()[0]
                == 0
            )
    finally:
        db.close()


def response(status=200, html=None):
    return Mock(status_code=status, content=(html or card_html()).encode(), headers={})


@pytest.mark.parametrize(
    "responses, status, reason, failed",
    [
        ([response()], "complete", "page_limit", 0),
        (
            [response(html='<p data-empty="true">No products</p>')],
            "empty",
            "source_end",
            0,
        ),
        ([response(403)], "failed", "page_limit", 1),
        ([response(html="<html>Changed layout</html>")], "failed", "page_limit", 1),
        ([response(), response(403)], "partial", "page_limit", 1),
    ],
)
def test_static_outcomes(responses, status, reason, failed):
    scraper = StaticScraper("https://source.test/products", delay=0, max_attempts=1)
    try:
        with patch.object(scraper.session, "get", side_effect=responses):
            result = scraper.scrape(max_pages=len(responses))
        assert result.status == status
        assert result.stop_reason == reason
        assert result.manifest()["pages_failed"] == failed
    finally:
        scraper.close()


def test_retries_rate_limit_and_repeated_page_budget():
    scraper = StaticScraper(
        "https://source.test/products?category=games",
        delay=0,
        max_attempts=2,
        page_budget=10,
    )
    try:
        with (
            patch.object(
                scraper.session,
                "get",
                side_effect=[response(503), response(), response()],
            ) as fetch,
            patch("scraper.product_scraper.time.sleep"),
        ):
            result = scraper.scrape()
        assert result.status == "partial"
        assert result.stop_reason == "repeated_page"
        assert result.pages[0].attempts == 2
        assert "category=games&page=2" in fetch.call_args.args[0]
        assert len(result.pages) == 2
    finally:
        scraper.close()


def test_rejected_pages_use_failure_budget_and_allow_later_recovery():
    rejected = '<div class="product-card">Missing title</div>'
    scraper = StaticScraper("https://source.test/products", delay=0)
    try:
        with patch.object(
            scraper.session,
            "get",
            side_effect=[
                response(html=rejected),
                response(html=rejected),
                response(),
                response(html='<p data-empty="true">No products</p>'),
            ],
        ) as fetch:
            run = scraper.scrape(4)
        assert fetch.call_count == 4
        assert run.status == "partial"
        assert run.stop_reason == "source_end"
        assert len(run.products) == 1
        assert run.manifest()["pages_failed"] == 2
        assert run.pages[0].fingerprint is None
    finally:
        scraper.close()


@pytest.mark.parametrize(
    "html, product_count, source_end",
    [
        (card_html(), 1, False),
        (
            card_html() + '<a rel="next" aria-disabled="true">Next</a>',
            1,
            True,
        ),
        ('<p data-empty="true">No products</p>', 0, True),
    ],
)
def test_static_deadline_retains_late_response_without_claiming_completion(
    html, product_count, source_end
):
    scraper = StaticScraper("https://source.test/products", delay=0, run_timeout=1)
    elapsed = [0.0]

    def finish_after_deadline(*args, **kwargs):
        elapsed[0] = 2.0
        return response(html=html)

    try:
        with (
            patch(
                "scraper.product_scraper.time.monotonic",
                side_effect=lambda: elapsed[0],
            ),
            patch.object(scraper.session, "get", side_effect=finish_after_deadline),
        ):
            run = scraper.scrape(1)
        assert run.status == "partial"
        assert run.stop_reason == "deadline"
        assert len(run.products) == product_count
        assert run.pages[0].source_end is source_end
        assert run.finished_at is not None
    finally:
        scraper.close()


def test_static_cancellation_between_pages_finishes_run_and_keeps_products():
    scraper = StaticScraper("https://source.test/products", delay=1)
    try:
        with (
            patch.object(scraper.session, "get", return_value=response()),
            patch("scraper.product_scraper.time.sleep", side_effect=KeyboardInterrupt),
            pytest.raises(KeyboardInterrupt),
        ):
            scraper.scrape(2)
        run = scraper.last_run
        assert run.status == "cancelled"
        assert run.stop_reason == "cancelled"
        assert run.finished_at is not None
        assert len(run.products) == 1
        assert len(run.pages) == 1
    finally:
        scraper.close()


@pytest.mark.parametrize("allow, expected_export", [(False, False), (True, True)])
def test_partial_cli_saves_evidence_and_requires_explicit_publication(
    tmp_path, allow, expected_export
):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'products.db'}")
    product = Product(
        name="Valid", price=None, source_id="1", source_url="https://source.test"
    )
    run = ScrapeRunResult(
        "https://source.test",
        2,
        "browser",
        pages=[
            PageResult(1, "https://source.test", status="success", products=[product]),
            PageResult(
                2, "https://source.test?page=2", errors=["HTTP 503"], http_status=503
            ),
        ],
    ).finish("page_limit")
    with (
        patch("main.DatabaseManager", return_value=db),
        patch("main._create_scraper") as factory,
        patch("main.DATA_DIR", tmp_path),
        patch.object(db, "export_for_powerbi") as export,
        patch("main._generate_pipeline_dashboards") as render,
    ):
        factory.return_value.scrape.return_value = run
        result = CliRunner().invoke(
            app, ["scrape"] + (["--allow-partial"] if allow else [])
        )
        assert result.exit_code == 2, result.output
        assert export.called is expected_export
        assert render.called is expected_export
        factory.return_value.close.assert_called_once()
    manifest = json.loads((tmp_path / "runs" / f"{run.run_id}.json").read_text())
    assert manifest["status"] == "partial" and manifest["missing_prices"] == 1
    assert manifest["pages_failed"] == 1
    reopened = DatabaseManager(f"sqlite:///{tmp_path / 'products.db'}")
    try:
        assert len(reopened.get_all_products()) == 1
        assert reopened.get_latest_run()["status"] == "partial"
    finally:
        reopened.close()


def test_model_validation_and_variant_identity():
    validated = Product.model_validate(
        {
            "name": "  Validated  ",
            "price": None,
            "source_url": "https://source.test",
            "source_id": "1",
        }
    )
    assert validated.name == "Validated"
    first = parse_page(
        card_html(identity="1?variant=red"), "https://source.test/products", 1
    ).products[0]
    second = parse_page(
        card_html(identity="1?variant=blue"), "https://source.test/products", 1
    ).products[0]
    assert first.source_key != second.source_key


def test_rejected_cards_make_run_partial_without_discarding_valid_cards():
    page = parse_page(
        card_html() + '<div class="product-card">Missing title</div>',
        "https://source.test",
        1,
    )
    run = ScrapeRunResult("https://source.test", 1, "static", pages=[page]).finish(
        "page_limit"
    )
    assert len(run.products) == 1
    assert run.status == "partial"
    assert run.manifest()["rejected_cards"] == 1


def test_complete_and_failed_cli_exit_codes(tmp_path):
    for status, code in [("empty", 0), ("failed", 1)]:
        db = DatabaseManager(f"sqlite:///{tmp_path / (status + '.db')}")
        page = PageResult(1, "https://source.test", status=status)
        run = ScrapeRunResult("https://source.test", 1, "browser", pages=[page]).finish(
            "page_limit"
        )
        with (
            patch("main.DatabaseManager", return_value=db),
            patch("main._create_scraper") as factory,
            patch("main.DATA_DIR", tmp_path),
        ):
            factory.return_value.scrape.return_value = run
            result = CliRunner().invoke(
                app, ["scrape", "--no-dashboard", "--no-export"]
            )
            assert result.exit_code == code, result.output
            assert (tmp_path / "runs" / f"{run.run_id}.json").exists()


@pytest.mark.parametrize("stop_reason", ["source_end", "deadline"])
def test_speculative_failures_beyond_confirmed_end_do_not_corrupt_scope(stop_reason):
    run = ScrapeRunResult(
        "https://source.test",
        3,
        "browser",
        pages=[
            PageResult(
                1,
                "https://source.test",
                status="success",
                source_end=True,
                products=[
                    Product(
                        name="Only product", price=0, source_url="https://source.test"
                    )
                ],
            ),
            PageResult(2, "https://source.test?page=2", errors=["HTTP 404"]),
            PageResult(3, "https://source.test?page=3", errors=["HTTP 503"]),
        ],
    ).finish(stop_reason)
    assert run.status == "complete"
    assert run.stop_reason == "source_end"
    manifest = run.manifest()
    assert manifest["pages_attempted"] == 3
    assert manifest["pages_succeeded"] == 1
    assert manifest["pages_failed"] == 0
    assert manifest["pages_outside_scope"] == 2
    assert manifest["pages"][1]["errors"] == ["HTTP 404"]


def test_concurrent_upsert_preserves_unique_identity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db = DatabaseManager(f"sqlite:///{tmp_path / 'concurrent.db'}")
    try:
        db.init_db()
        with ThreadPoolExecutor(max_workers=2) as pool:
            writes = [
                pool.submit(
                    db.save_products,
                    [
                        Product(
                            name=f"Name {price}",
                            price=price,
                            source_id="same",
                            source_url="https://source.test",
                        )
                    ],
                )
                for price in (10, 20)
            ]
            for write in writes:
                write.result()
        rows = db.get_all_products()
        assert len(rows) == 1
        assert rows[0].price in (10, 20)
    finally:
        db.close()
