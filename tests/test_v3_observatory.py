"""Tests for ScrapingStore 3.0 features: report, data checks, reparse, MockMarket, adapters."""

from __future__ import annotations

import csv
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st
from typer.testing import CliRunner

from scrapingstore.analytics.insights import (
    censored_restock_analysis,
    detect_franchises_tfidf,
    detect_possibly_delisted,
)
from scrapingstore.cli.app import _persist_collection, app
from scrapingstore.cli.server import create_server
from scrapingstore.config import get_settings
from scrapingstore.io_utils import atomic_write_text, escape_csv_cell
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.ledger.models import Product, price_to_minor
from scrapingstore.quality.gates import evaluate_quality_gate
from scrapingstore.quality.smells import detect_smells, ks_statistic
from scrapingstore.report.columnar import decode_columnar, encode_columnar
from scrapingstore.report.generator import generate_dashboard
from scrapingstore.sources.base import parse_price
from scrapingstore.sources.mock_market import MockMarket
from scrapingstore.sources.oxylabs import parse_page
from scrapingstore.sources.recipe import JsonLdAdapter, RecipeAdapter
from scrapingstore.transport.archive import reparse_run

runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Lazy-load image & genre extraction fixes
# ---------------------------------------------------------------------------


def test_lazy_image_extraction_rejects_gif_and_recovers_genre():
    html = """
    <html><body>
      <div class="product-card" data-product-id="42" data-rating="4.8">
        <a class="card-header" href="/products/42"><h4>Chrono Trigger</h4></a>
        <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="/assets/role-playing.svg">
        <div class="price-wrapper">59,99 €</div>
        <span class="availability">In Stock</span>
      </div>
      <div class="product-card" data-product-id="43">
        <a class="card-header" href="/products/43"><h4>Placeholder Only</h4></a>
        <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
        <div class="price-wrapper">19,99 €</div>
        <span class="availability">Out of Stock</span>
      </div>
    </body></html>
    """
    page = parse_page(html, "https://sandbox.oxylabs.io/products", 1)
    assert page.status == "success"
    p1, p2 = page.products
    assert p1.image_url == "https://sandbox.oxylabs.io/assets/role-playing.svg"
    assert p1.category == "Role-Playing"
    assert p1.rating == 4.8
    assert p1.price_minor == 5999
    assert p2.image_url is None
    assert p2.category is None


# ---------------------------------------------------------------------------
# 2. Universal JSON-LD and Declarative TOML Recipe adapters
# ---------------------------------------------------------------------------


def test_jsonld_adapter_extracts_schema_org_products():
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [{
          "@type": "ListItem",
          "position": 1,
          "item": {
            "@type": "Product",
            "name": "Mechanical Keyboard",
            "sku": "KB-900",
            "category": "Hardware",
            "image": "/img/kb.png",
            "url": "/p/kb-900",
            "aggregateRating": {"ratingValue": 4.7},
            "offers": {
              "@type": "Offer",
              "price": "149.99",
              "priceCurrency": "EUR",
              "availability": "https://schema.org/InStock"
            }
          }
        }]
      }
      </script>
    </head><body></body></html>
    """
    res = JsonLdAdapter().parse_page(html, "https://shop.test/catalog", 1)
    assert res.status == "success"
    assert len(res.products) == 1
    p = res.products[0]
    assert p.name == "Mechanical Keyboard"
    assert p.source_id == "KB-900"
    assert p.price == 149.99
    assert p.availability == "In Stock"
    assert p.category == "Hardware"
    assert p.rating == 4.7


def test_recipe_adapter_from_toml(tmp_path):
    recipe_file = tmp_path / "store.toml"
    recipe_file.write_text(
        """
[recipe]
name = "books"
card_selector = "article.book"
title_selector = "h3"
price_selector = ".cost"
availability_selector = ".stock"
category_selector = ".tag"
link_selector = "a.detail"
id_attr = "data-sku"
""",
        encoding="utf-8",
    )
    adapter = RecipeAdapter.from_toml(recipe_file)
    html = """
    <article class="book" data-sku="BK-1">
      <a class="detail" href="/books/1"><h3>Dune</h3></a>
      <span class="cost">14.50 €</span>
      <span class="stock">In Stock</span>
      <span class="tag">Sci-Fi</span>
    </article>
    """
    res = adapter.parse_page(html, "https://books.test/", 1)
    assert res.status == "success"
    assert res.products[0].name == "Dune"
    assert res.products[0].source_id == "BK-1"
    assert res.products[0].category == "Sci-Fi"


# ---------------------------------------------------------------------------
# 3. Hypothesis property-based tests for parse_price
# ---------------------------------------------------------------------------


@given(cents=st.integers(min_value=0, max_value=999_999_99))
def test_parse_price_roundtrips_all_non_negative_eur_cents(cents: int):
    major = cents / 100
    raw = f"{major:.2f} €"
    parsed = parse_price(raw)
    assert parsed.status == "known"
    assert parsed.value == pytest.approx(major)
    assert price_to_minor(parsed.value) == cents


@given(val=st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False))
def test_parse_price_rejects_negative_values(val: float):
    parsed = parse_price(f"{val:.2f} €")
    assert parsed.value is None
    assert parsed.status == "invalid"


# ---------------------------------------------------------------------------
# 4. Quality Gates (`degraded`) & Auto Data Forensics (`smells`)
# ---------------------------------------------------------------------------


def test_quality_gate_promotes_silent_price_drift_to_degraded():
    baseline_products = [
        Product(name=f"Item {i}", price=20.0 + i, source_id=str(i), source_url="https://x.test")
        for i in range(20)
    ]
    baseline_gate = evaluate_quality_gate(baseline_products)
    assert baseline_gate["passed"] is True

    drifted_products = [
        Product(
            name=f"Item {i}",
            price=None if i < 12 else 20.0,
            source_id=str(i),
            source_url="https://x.test",
        )
        for i in range(20)
    ]
    prior = [{"status": "complete", "quality_gate": baseline_gate}]
    gate = evaluate_quality_gate(drifted_products, prior_runs=prior)
    assert gate["passed"] is False
    assert gate["status"] == "degraded"
    assert any("price_selector_drift" in r for r in gate["reasons"])


def test_smells_detects_synthetic_alternation_placeholders_and_ladder():
    fixed_ts = datetime(2025, 12, 11, 16, 14, 29, tzinfo=timezone.utc)
    products = [
        Product(
            name=f"Game {i}",
            price=59.99 + (i % 5),
            availability="In Stock" if i % 2 == 0 else "Out of Stock",
            image_url="data:image/gif;base64,R0lGOD" if i % 2 == 0 else "/assets/action.svg",
            source_url="https://sandbox.test",
            scraped_at=fixed_ts,
        )
        for i in range(40)
    ]
    smells = detect_smells(products)
    codes = {s.code for s in smells}
    assert "lazy_placeholder_images" in codes
    assert "synthetic_stock_alternation" in codes
    assert "discrete_pricing_ladder" in codes
    assert "constant_timestamps" in codes
    assert "weak_identity_dominance" in codes
    assert ks_statistic([10, 20, 30], [80, 90, 100]) == 1.0


# ---------------------------------------------------------------------------
# 5. Columnar Compression, TF-IDF Franchises, Censored Restocks & Delisting
# ---------------------------------------------------------------------------


def test_columnar_codec_roundtrips_and_compresses():
    rows = [
        {
            "name": f"Super Mario Game {i}",
            "price": 59.99,
            "availability": "In Stock",
            "category": "Platformer",
            "rating": 4.8,
            "currency": "EUR",
            "price_status": "known",
            "price_raw": "59,99 €",
            "image_url": "https://x.test/assets/platformer.svg",
            "product_url": f"https://x.test/products/{i}",
            "source_key": f"x.test:id:{i}",
            "identity_kind": "native",
            "scraped_at": "2025-12-11T16:14:29Z",
            "freshness": "stale",
            "freshness_label": "Observed over 7 days ago",
            "observed_age_days": 347.0,
            "last_run_id": "run-1",
            "parser_version": "3.0",
            "availability_reason": None,
        }
        for i in range(200)
    ]
    bundle = encode_columnar(rows)
    decoded = decode_columnar(bundle)
    assert decoded == rows
    raw_len = len(json.dumps(rows))
    comp_len = len(json.dumps(bundle))
    assert comp_len < raw_len * 0.35


def test_tfidf_franchises_suppresses_roman_numerals_and_stopwords():
    rows = [
        {"name": "Super Mario Odyssey"},
        {"name": "Super Mario Galaxy"},
        {"name": "Super Mario Maker 2"},
        {"name": "Mega Man X Legacy Collection"},
        {"name": "Mega Man Zero"},
        {"name": "Episode III World War Age"},
        {"name": "Episode III World War Age"},
    ]
    franchises = detect_franchises_tfidf(rows)
    names = [f["name"] for f in franchises]
    assert "Super Mario" in names
    assert "Mega Man" in names
    assert "Iii" not in names and "III" not in names
    assert "World" not in names and "War" not in names


def test_mock_market_censored_restocks_delisting_blame_and_reparse(tmp_path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'market.db'}")
    try:
        db.init_db()
        market = MockMarket(seed=42, sku_count=48, per_page=24)
        run_ids = []
        for ep in range(5):
            run = market.collect_epoch(ep)
            _persist_collection(db, run, data_dir=tmp_path, archive_html=True)
            run_ids.append(run.run_id)

        # Epoch 3 intentionally triggers degraded quality gate
        assert db.get_run(run_ids[3])["status"] == "degraded"
        assert db.resolve_run_id("@latest") == run_ids[4]
        assert db.resolve_run_id("@prev") == run_ids[3]
        assert db.resolve_run_id(run_ids[0][:8]) == run_ids[0]

        # Multi-run history, censored restocks & confidence-graded delistings
        history = db.get_multi_run_history(limit=10)
        assert len(history) == 5
        restocks = censored_restock_analysis(history)
        assert restocks["runs_analyzed"] == 5
        assert restocks["completed_restocks"] >= 1
        delisted = detect_possibly_delisted(history, min_consecutive_misses=2)
        assert len(delisted) == 3

        # Blame provenance
        blame = db.blame_product("Super Mario")
        assert blame["observations_count"] == 5
        assert "price" in blame["fields"]

        # Time-travel reparse from content-addressed gzipped raw HTML
        reparsed = reparse_run(db, run_ids[0], apply=False)
        assert reparsed["pages_replayed"] == 2
        assert reparsed["reparsed_products"] == 48
        assert reparsed["applied"] is False

        # The report shows all five runs, with the degraded one marked
        out_html = tmp_path / "report.html"
        generate_dashboard(db, output_path=str(out_html))
        html = out_html.read_text(encoding="utf-8")
        assert 'id="columnar-data"' in html
        timeline = json.loads(
            html.split('<script id="timeline-data" type="application/json">', 1)[1].split(
                "</script>", 1
            )[0]
        )
        assert [run["id"] for run in timeline["runs"]] == run_ids
        assert timeline["runs"][3]["status"] == "degraded"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 6. CSV Formula Guard, Atomic Writes, Live Server & Config Laziness
# ---------------------------------------------------------------------------


def test_server_csv_escapes_formulas_and_writes_atomically(tmp_path):
    assert escape_csv_cell("=CMD|' /C calc'!A0").startswith("'=")
    assert escape_csv_cell("+1+1").startswith("'+")
    target = tmp_path / "atomic.txt"
    atomic_write_text(target, "safe")
    assert target.read_text(encoding="utf-8") == "safe"

    db = DatabaseManager(f"sqlite:///{tmp_path / 'csv.db'}")
    try:
        db.init_db()
        db.save_products(
            [Product(name="=1+1", source_url="https://x.test", source_id="1", price=5.0)]
        )
        csv_path = tmp_path / "powerbi.csv"
        assert db.export_for_powerbi(str(csv_path)) is True
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["name"] == "'=1+1"
    finally:
        db.close()


def test_config_is_lazy_and_honest_user_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path / "nonexistent_ws"))
    monkeypatch.delenv("DATA_DIR", raising=False)
    settings = get_settings(load_env=False)
    assert not settings.data_dir.exists()
    assert "ScrapingStore/" in settings.user_agent
    assert "Chrome/120" not in settings.user_agent


def test_live_server_serves_report_and_status(tmp_path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'srv.db'}")
    db.init_db()
    db.save_products([Product(name="Live Item", source_url="https://x.test", price=12.99)])
    server = create_server(db, host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status") as resp:
            status = json.loads(resp.read().decode("utf-8"))
        assert status["products"] == 1
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            body = resp.read().decode("utf-8")
        assert "Live Item" in body
        assert 'id="timeline-data"' in body
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/dashboard_terminal.html")
        assert missing.value.code == 404
        missing.value.close()
    finally:
        server.shutdown()
        server.server_close()
        db.close()


def test_cli_doctor_and_demo_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("DOCS_DIR", raising=False)
    res_doc = runner.invoke(app, ["doctor"])
    assert res_doc.exit_code == 0, res_doc.output
    assert "ScrapingStore" in res_doc.output

    res_demo = runner.invoke(app, ["demo", "--epochs", "3"])
    assert res_demo.exit_code == 0, res_demo.output
    assert (tmp_path / "data" / "dashboard.html").exists()
    assert not (tmp_path / "data" / "dashboard_terminal.html").exists()
