"""The product x run timeline only claims changes the observations support."""

from datetime import datetime, timedelta, timezone

from scrapingstore.analytics.comparison import compare_observations
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.ledger.models import Product
from scrapingstore.report.timeline import (
    COMPARED_WITH,
    PRICE,
    PRICE_CHANGE,
    STOCK,
    STOCK_CHANGE,
    build_timeline,
)
from scrapingstore.sources.mock_market import MockMarket
from tests.test_history import product

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def manifest(index, status="complete"):
    return {
        "run_id": f"run-{index}",
        "started_at": START + timedelta(days=7 * index),
        "status": status,
    }


def history(*runs):
    """runs: one list of products per run, oldest first."""
    return [(manifest(i), list(products)) for i, products in enumerate(runs)]


def row(timeline, name="Original title"):
    return next(r for r in timeline["rows"] if r["name"] == name)


def test_drop_between_consecutive_runs_is_certain():
    timeline = build_timeline(history([product(price=20)], [product(price=15)]))
    cells = row(timeline)["cells"]
    assert cells[1][PRICE] == 15
    assert cells[1][PRICE_CHANGE] == "down"
    assert cells[1][COMPARED_WITH] == 0
    assert timeline["latest"]["dropped"] == 1
    assert timeline["latest"]["dropped_gap"] == 0


def test_change_across_an_unreadable_price_is_a_gap_change():
    timeline = build_timeline(
        history([product(price=20)], [product(price=None)], [product(price=25)])
    )
    cells = row(timeline)["cells"]
    assert cells[1][PRICE] is None and cells[1][PRICE_CHANGE] == ""
    assert cells[2][PRICE_CHANGE] == "up_gap"
    assert cells[2][COMPARED_WITH] == 0
    assert timeline["latest"]["rose"] == 0
    assert timeline["latest"]["rose_gap"] == 1


def test_change_across_a_run_that_missed_the_product_is_a_gap_change():
    other = product(source_id="other", name="Other", product_url="https://source.test/o")
    timeline = build_timeline(
        history([product(price=20), other], [other], [product(price=10), other])
    )
    cells = row(timeline)["cells"]
    assert cells[1] is None
    assert cells[2][PRICE_CHANGE] == "down_gap"
    assert timeline["latest"]["dropped"] == 0
    assert timeline["latest"]["dropped_gap"] == 1


def test_same_price_within_a_cent_is_not_a_change():
    timeline = build_timeline(history([product(price=9.99)], [product(price=9.990000001)]))
    assert row(timeline)["cells"][1][PRICE_CHANGE] == ""


def test_stock_changes_only_compare_with_the_previous_run():
    out = {"availability": "Out of Stock"}
    other = product(source_id="other", name="Other", product_url="https://source.test/o")
    timeline = build_timeline(
        history([product(**out), other], [other], [product(), other], [product(**out), other])
    )
    cells = row(timeline)["cells"]
    assert [c and c[STOCK] for c in cells] == ["out", None, "in", "out"]
    assert cells[2][STOCK_CHANGE] == ""
    assert cells[3][STOCK_CHANGE] == "out"
    assert timeline["latest"]["sold_out"] == 1
    assert timeline["latest"]["back_in_stock"] == 0


def test_products_without_a_stable_identity_are_never_compared():
    def weak(price):
        return Product(name="No ID", source_url="https://source.test", price=price)

    timeline = build_timeline(history([weak(10)], [weak(5)]))
    rows = [r for r in timeline["rows"] if r["name"] == "No ID"]
    # Weak keys never match across runs, so each observation is its own row.
    assert len(rows) == 2
    assert all(not r["comparable"] for r in rows)
    assert all(c[PRICE_CHANGE] == "" for r in rows for c in r["cells"] if c)
    assert timeline["latest"]["new"] == 0
    assert timeline["latest"]["not_seen"] == 0


def test_mixed_currency_prices_are_not_compared():
    timeline = build_timeline(
        history([product(price=10, currency="EUR")], [product(price=12, currency="USD")])
    )
    target = row(timeline)
    assert target["mixed_currency"] is True
    assert target["cells"][1][PRICE_CHANGE] == ""
    assert timeline["latest"]["rose"] == 0


def test_new_and_not_seen_products_count_against_the_previous_run_only():
    gone = product(source_id="gone", name="Gone", product_url="https://source.test/gone")
    fresh = product(source_id="fresh", name="Fresh", product_url="https://source.test/fresh")
    long_gone = product(source_id="lg", name="Long gone", product_url="https://source.test/lg")
    timeline = build_timeline(
        history([product(), gone, long_gone], [product(), gone], [product(), fresh])
    )
    assert timeline["latest"]["new"] == 1
    assert timeline["latest"]["not_seen"] == 1
    assert row(timeline, "Fresh")["first"] == 2
    assert row(timeline, "Gone")["last"] == 1
    assert row(timeline, "Long gone")["last"] == 0


def test_catalog_without_history_is_a_single_column():
    catalog = [
        product(scraped_at=START),
        product(source_id="b", name="B", scraped_at=START + timedelta(hours=3)),
    ]
    timeline = build_timeline(None, catalog)
    assert len(timeline["runs"]) == 1
    assert timeline["runs"][0]["started_at"] == "2026-09-01T03:00:00Z"
    assert timeline["runs"][0]["status"] == "unknown"
    assert timeline["latest"] is None
    assert {r["name"] for r in timeline["rows"]} == {"Original title", "B"}


def test_catalog_products_outside_the_embedded_runs_are_kept():
    old = product(
        source_id="old", name="Old", product_url="https://source.test/old", scraped_at=START
    )
    timeline = build_timeline(history([product()]), [product(), old])
    target = row(timeline, "Old")
    assert target["cells"] == [None]
    assert target["first"] is None and target["last"] is None
    assert target["last_seen"] == "2026-09-01T00:00:00Z"


def test_empty_inputs():
    assert build_timeline(None, []) == {"runs": [], "rows": [], "latest": None}


def test_showcase_headline_matches_the_run_comparison(tmp_path):
    from scrapingstore.cli.app import _persist_collection

    db = DatabaseManager(f"sqlite:///{tmp_path / 'demo.db'}")
    try:
        db.init_db()
        market = MockMarket(seed=42, sku_count=96, per_page=24)
        for epoch in range(5):
            _persist_collection(db, market.collect_epoch(epoch), data_dir=tmp_path)
        runs = db.get_multi_run_history(limit=5)
    finally:
        db.close()

    latest = build_timeline(runs)["latest"]
    (old_run, old_products), (new_run, new_products) = runs[-2], runs[-1]
    summary = compare_observations(old_run, new_run, old_products, new_products)["summary"]
    assert latest["dropped"] == summary["price_drops"]
    assert latest["rose"] == summary["price_rises"]
    assert latest["back_in_stock"] == summary["restocks"]
    assert latest["sold_out"] == summary["stockouts"]
    assert latest["new"] == summary["only_in_new"]
    assert latest["not_seen"] == summary["only_in_old"]
    # The degraded run hides when some prices changed; those are counted apart.
    assert latest["dropped_gap"] + latest["rose_gap"] > 0
