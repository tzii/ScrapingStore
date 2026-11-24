"""Real Chromium tests for the offline HTML report (run with --run-browser)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from scrapingstore.ledger.models import Product
from scrapingstore.report.generator import generate_dashboard
from scrapingstore.report.snapshot import ReportSnapshot


@pytest.fixture
def report_page(request, tmp_path):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser to run the browser regressions")

    external_requests: list[str] = []

    def respond(route):
        url = route.request.url
        if url.startswith("https://reports.test/"):
            path = tmp_path / unquote(urlsplit(url).path.lstrip("/"))
            route.fulfill(path=path, content_type="text/html")
        else:
            external_requests.append(url)
            route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            reduced_motion="reduce",
            viewport={"width": 1440, "height": 1000},
            locale="en-GB",
            timezone_id="UTC",
        )
        context.route("**/*", respond)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        context.close()
        browser.close()
        assert errors == [], f"JS page errors: {errors}"
        assert external_requests == [], f"Unexpected external requests: {external_requests}"


def render(tmp_path, snapshot, name="dashboard.html"):
    generate_dashboard(snapshot, str(tmp_path / name))
    return "https://reports.test/" + name


def download_rows(page):
    with page.expect_download() as download:
        page.get_by_role("button", name="Export matching products as CSV").click()
    text = Path(download.value.path()).read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def item(key, price, availability="In Stock"):
    return Product(
        name=f"Product {key}",
        source_id=key,
        source_url="https://example.test",
        product_url=f"https://example.test/products/{key}",
        price=price,
        availability=availability,
        category="Games",
    )


def three_runs():
    """A drops, B rises, C changes across an unreadable price, D restocks, F is new, G vanishes."""
    run_products = [
        [
            item("A", 20),
            item("B", 10),
            item("C", 30),
            item("D", 40, "Out of Stock"),
            item("E", 50),
            item("G", 60),
        ],
        [
            item("A", 20),
            item("B", 10),
            item("C", None),
            item("D", 40, "Out of Stock"),
            item("E", 50),
            item("G", 60),
        ],
        [item("A", 15), item("B", 12), item("C", 25), item("D", 40), item("E", 50), item("F", 70)],
    ]
    statuses = ["complete", "degraded", "complete"]
    history = [
        (
            {
                "run_id": f"run-{i}",
                "started_at": f"2026-09-{1 + 7 * i:02d}T10:00:00+00:00",
                "status": statuses[i],
            },
            products,
        )
        for i, products in enumerate(run_products)
    ]
    catalog = run_products[2] + [run_products[1][5]]
    return ReportSnapshot.from_products(
        catalog,
        run=history[-1][0],
        history=history,
        generated_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
    )


def test_headline_counts_filter_the_table_and_the_export(report_page, tmp_path):
    page = report_page
    page.goto(render(tmp_path, three_runs()))
    lede = page.locator("#lede")
    expect(lede).to_have_text(
        "On 15 Sep, ▼1 price dropped, ▲1 rose, 1 product came back in stock, "
        "1 new product appeared and 1 wasn't seen."
    )
    expect(page.locator("#status")).to_have_text("6 of 7 products changed over these 3 runs")
    expect(page.locator("#grid tbody tr")).to_have_count(6)
    expect(page.locator("#grid thead")).to_contain_text("83% read")

    drop = lede.locator('button[data-ev="drop"]')
    drop.click()
    expect(drop).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#status")).to_contain_text("1 product whose price dropped on 15 Sep")
    expect(page.locator("#grid tbody tr")).to_have_count(1)
    expect(page.locator("#grid tbody")).to_contain_text("Product A")
    assert [row["name"] for row in download_rows(page)] == ["Product A"]

    page.get_by_role("button", name="Show all changes").click()
    expect(page.locator("#grid tbody tr")).to_have_count(6)
    page.get_by_role("button", name="Show the 1 product that didn't change").click()
    expect(page.locator("#grid tbody tr")).to_have_count(7)
    assert len(download_rows(page)) == 7

    page.get_by_label("Search products").fill("zzz")
    expect(page.locator("#grid")).to_contain_text("No products match.")
    page.keyboard.press("Escape")
    expect(page.locator("#grid tbody tr")).to_have_count(7)


def test_gap_changes_are_marked_and_explained(report_page, tmp_path):
    page = report_page
    page.goto(render(tmp_path, three_runs()))
    row = page.locator("#grid tbody tr", has_text="Product C")
    expect(row.locator('td[data-i="2"] .v')).to_have_text("▽25.00")
    row.locator('td[data-i="2"]').hover()
    expect(page.locator("#tip")).to_contain_text("Down €5.00 since 1 Sep")
    expect(page.locator("#tip")).to_contain_text("the run it changed in is unknown")
    notes = page.locator("#notes")
    expect(notes).to_contain_text("8 Sep run was degraded.")
    expect(notes).to_contain_text("1 not seen since 8 Sep: Product G.")
    expect(page.locator("#legend")).to_contain_text("Changed, run unknown")


def hover_run(page, chart, run_index):
    svg = page.locator(f"#{chart}")
    box = svg.bounding_box()
    band = page.locator(f'#{chart} rect.band[data-i="{run_index}"]').bounding_box()
    svg.hover(position={"x": band["x"] - box["x"] + band["width"] / 2, "y": 4})


def test_charts_summarise_the_runs(report_page, tmp_path):
    page = report_page
    page.goto(render(tmp_path, three_runs()))
    expect(page.locator("#overview")).to_be_visible()
    # A 20→15 and B 10→12 between the last two runs that read their prices; D and E held.
    expect(page.locator("#index-title")).to_have_text("Prices down 2.6% since 1 Sep")
    expect(page.locator("#changes-title")).to_have_text("3 price changes since 1 Sep")
    expect(page.locator("#changes-key")).to_contain_text("Run unknown")
    expect(page.locator("#stock-title")).to_have_text("6 of 6 in stock on 15 Sep")
    expect(page.locator("#chart-index circle.pt.hollow")).to_have_count(1)
    expect(page.locator("#chart-changes path.gap")).to_have_count(1)

    hover_run(page, "chart-changes", 2)
    tip = page.locator("#tip")
    expect(tip).to_contain_text("1 dropped, 1 rose since the previous run")
    expect(tip).to_contain_text("1 more changed across a run that couldn't read them")
    expect(page.locator('#chart-stock rect.band.on[data-i="2"]')).to_have_count(1)

    expect(page.locator("#prices-title")).to_have_text("Prices on 15 Sep")
    expect(page.locator("#chart-prices circle.dot")).to_have_count(6)
    expect(page.locator("#restock-title")).to_have_text("Restocks took about 2 weeks")

    page.locator('#lede button[data-ev="drop"]').click()
    expect(page.locator("#chart-prices circle.dot:not(.dim)")).to_have_count(1)

    page.set_viewport_size({"width": 390, "height": 844})
    # The report redraws shortly after a resize; wait for it rather than for a fixed time.
    page.wait_for_function("document.documentElement.scrollWidth <= 390")
    assert page.evaluate("document.getElementById('chart-stock').viewBox.baseVal.width") <= 358


def test_single_run_freshness_csv_theme_and_mobile(report_page, tmp_path):
    observed = Product(
        name="Older observation",
        price=0,
        availability="In Stock",
        category="Action",
        source_url="https://example.test",
        scraped_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    page = report_page
    page.goto(render(tmp_path, ReportSnapshot.from_products([observed])))
    expect(page.locator("#lede")).to_have_text("1 product, 1 in stock.")
    expect(page.locator("#overview")).to_be_hidden()
    expect(page.locator("#restock")).to_be_hidden()
    expect(page.locator("#prices")).to_be_hidden()
    expect(page.locator("#freshness")).to_contain_text("days old")
    expect(page.locator("#grid tbody")).to_contain_text("0.00")
    row = download_rows(page)[0]
    assert row["freshness"] == "stale" and row["availability"] == "In Stock"
    assert row["price"] == "0"

    page.get_by_role("button", name="Switch theme").click()
    theme = page.evaluate("document.documentElement.dataset.theme")
    assert theme in ("light", "dark")
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == theme

    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth") <= 390


def test_hostile_text_zero_price_and_missing_price_separation(report_page, tmp_path):
    hostile = '=1+1, "quoted" </script><script>window.pwned=true</script>'
    products = [
        Product(name=hostile, price=0, availability="Unknown", source_url="https://example.test"),
        Product(name="Unknown price", price=None, source_url="https://example.test"),
        Product(name="Paid product", price=10, source_url="https://example.test"),
    ]
    page = report_page
    page.goto(render(tmp_path, ReportSnapshot.from_products(products)))
    expect(page.locator("#facts")).to_contain_text("Median price €5.00.")
    unknown = page.locator("#grid tbody tr", has_text="Unknown price")
    expect(unknown.locator(".v")).to_have_text("?")
    assert page.evaluate("window.pwned === undefined")

    exported = download_rows(page)
    assert next(p for p in exported if p["name"] == "Unknown price")["price"] == ""
    assert next(p for p in exported if "quoted" in p["name"])["name"] == "'" + hostile


def test_prices_use_the_stores_main_currency(report_page, tmp_path):
    products = [
        Product(
            name=f"Item {n}",
            price=n * 10,
            currency="USD",
            category="Tools",
            source_url="https://example.test",
        )
        for n in range(1, 5)
    ] + [
        Product(
            name="Import",
            price=99,
            currency="GBP",
            category="Tools",
            source_url="https://example.test",
        )
    ]
    page = report_page
    page.goto(render(tmp_path, ReportSnapshot.from_products(products)))
    expect(page.locator("#facts")).to_contain_text("Median price 25.00 USD.")
    expect(page.locator("#prices")).to_be_visible()
    expect(page.locator("#chart-prices circle.dot")).to_have_count(4)
    expect(page.locator("#chart-prices")).to_contain_text("median 25.00 USD")


def test_empty_report_says_so(report_page, tmp_path):
    page = report_page
    page.goto(render(tmp_path, ReportSnapshot.from_products([])))
    expect(page.get_by_text("No data yet.")).to_be_visible()
    expect(page.locator("#report")).to_be_hidden()
