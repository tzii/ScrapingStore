"""Exercise the generated reports using real Alpine, Grid.js and Chart.js locally."""

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from models import Product
from visualization.dashboard_generator import generate_dashboard
from visualization.report_data import ReportSnapshot
from visualization.terminal_dashboard_generator import generate_terminal_dashboard

ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = {
    "https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js": "alpinejs/dist/cdn.min.js",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js": "chart.js/dist/chart.umd.js",
    "https://unpkg.com/gridjs@6.2.0/dist/gridjs.umd.js": "gridjs/dist/gridjs.umd.js",
}


@pytest.fixture
def report_page(request, tmp_path):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser to run the browser regressions")
    for dependency in LIBRARIES.values():
        assert (
            ROOT / "node_modules" / dependency
        ).exists(), "Run npm ci before browser tests"

    def respond(route):
        url = route.request.url
        if url in LIBRARIES:
            route.fulfill(
                path=ROOT / "node_modules" / LIBRARIES[url],
                content_type="text/javascript",
            )
        elif url.startswith("https://reports.test/"):
            path = tmp_path / unquote(urlsplit(url).path.lstrip("/"))
            route.fulfill(path=path, content_type="text/html")
        elif (
            url == "https://cdn.tailwindcss.com/"
            or url == "https://cdn.tailwindcss.com"
        ):
            # Styling is outside these behavior tests; no CDN or source-site requests.
            route.fulfill(body="window.tailwind = {};", content_type="text/javascript")
        else:
            route.fulfill(body="", content_type="text/css")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            reduced_motion="reduce", viewport={"width": 1440, "height": 1000}
        )
        context.route("**/*", respond)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        context.close()
        browser.close()
        assert errors == []


def render_pair(tmp_path, products, modern_name="dashboard.html"):
    snapshot = ReportSnapshot.from_products(products)
    modern = tmp_path / modern_name
    terminal = tmp_path / "dashboard_terminal.html"
    generate_dashboard(snapshot, str(modern), terminal_path=str(terminal))
    generate_terminal_dashboard(snapshot, str(terminal), dashboard_path=str(modern))
    return "https://reports.test/" + modern_name


def download_rows(page):
    with page.expect_download() as download:
        page.get_by_role("button", name="Export all matching products as CSV").click()
    text = Path(download.value.path()).read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_freshness_is_visible_and_exported_without_overriding_stock(
    report_page, tmp_path
):
    product = Product(
        name="Older observation",
        price=0,
        availability="In Stock",
        source_url="https://example.test",
        scraped_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    page = report_page
    page.goto(render_pair(tmp_path, [product]))
    expect(page.locator("#freshness")).to_contain_text("1 over 7 days old")
    expect(page.locator("#grid-table tbody")).to_contain_text(
        "Observed over 7 days ago"
    )
    expect(page.locator("#grid-table tbody")).to_contain_text("In Stock")
    row = download_rows(page)[0]
    assert row["freshness"] == "stale" and row["availability"] == "In Stock"
    assert row["price"] == "0"
    page.get_by_role("link", name="Terminal", exact=False).click()
    expect(page.locator("#freshness")).to_contain_text("1 over 7 days old")
    page.set_viewport_size({"width": 390, "height": 844})
    summary = page.locator(".price-summary")
    summary.scroll_into_view_if_needed()
    bounds = summary.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    assert page.evaluate("document.documentElement.scrollWidth") == 390
    expect(page.locator("#log-feed")).to_contain_text("Observed over 7 days ago")


def test_search_filters_pagination_and_export_agree(report_page, tmp_path):
    products = [
        Product(
            name=f"Match {i:02d}",
            price=10 + i,
            availability="In Stock",
            source_url="https://example.test",
        )
        for i in range(16)
    ] + [
        Product(
            name="Match unavailable",
            price=20,
            availability="Out of Stock",
            source_url="https://example.test",
        ),
        Product(
            name="Match expensive",
            price=50,
            availability="In Stock",
            source_url="https://example.test",
        ),
        Product(
            name="Unrelated",
            price=20,
            availability="In Stock",
            source_url="https://example.test",
        ),
    ]
    page = report_page
    page.goto(render_pair(tmp_path, products))
    expect(page.locator("#grid-table tbody tr")).to_have_count(12)
    page.get_by_label("Search catalog").fill("mAtCh")
    page.get_by_label("Filter by availability").select_option("In Stock")
    page.get_by_label("Minimum price").fill("10")
    page.get_by_label("Maximum price").fill("30")
    expect(page.locator("#catalog-match-count")).to_have_text("16 matching products")
    page.get_by_role("button", name="Next", exact=True).click()
    expect(page.locator("#grid-table tbody tr")).to_have_count(4)
    rows = download_rows(page)
    assert {row["name"] for row in rows} == {f"Match {i:02d}" for i in range(16)}
    assert len(rows) == 16
    # Summaries and charts remain the explicitly labelled full catalog.
    expect(page.locator("#kpi-total")).to_have_text("19")
    assert (
        page.evaluate(
            "Chart.getChart('priceChart').data.datasets[0].data.reduce((a,b) => a+b, 0)"
        )
        == 18
    )
    expect(page.locator("#price-outliers")).to_contain_text("1 high-price outlier")
    page.get_by_label("Search catalog").fill("Match 00")
    expect(page.locator("#grid-table tbody tr")).to_have_count(1)
    assert [row["name"] for row in download_rows(page)] == ["Match 00"]
    page.get_by_label("Search catalog").fill("no such product")
    expect(page.locator("#catalog-match-count")).to_have_text("0 matching products")
    assert download_rows(page) == []
    page.get_by_role("button", name="Reset", exact=True).click()
    expect(page.locator("#catalog-match-count")).to_have_text("19 matching products")
    expect(page.get_by_label("Search catalog")).to_have_value("")
    assert len(download_rows(page)) == 19


def test_dates_median_and_outliers_are_visible_without_empty_disclosure(
    report_page, tmp_path
):
    products = [
        Product(
            name=f"Price {price}",
            price=price,
            availability="In Stock",
            source_url="https://example.test",
            scraped_at=datetime(2025, 12, 11, tzinfo=timezone.utc),
        )
        for price in [50, 55, 60, 65, 70, 75, 80, 85] * 3 + [500, 800]
    ]
    page = report_page
    page.goto(render_pair(tmp_path, products))
    expect(page.locator("#observation-period")).to_contain_text(
        "Data collected 11 December 2025"
    )
    expect(page.locator("details#collection-outcome")).to_have_count(0)
    expect(page.locator("#kpi-median")).to_have_text("70.00")
    expect(page.locator("#price-outliers")).to_contain_text("2 high-price outliers")
    assert (
        page.evaluate(
            "Chart.getChart('priceChart').data.datasets[0].data.reduce((a,b) => a+b, 0)"
        )
        == 24
    )
    assert page.evaluate("Chart.getChart('priceChart').scales.y.width") >= 60
    for _ in range(2):
        page.get_by_role("button", name="Toggle color theme").click()
        expected_color = page.evaluate(
            "Alpine.store('theme').isDark ? '#a0a0ad' : '#706b66'"
        )
        assert (
            page.evaluate("Chart.getChart('priceChart').options.scales.y.ticks.color")
            == expected_color
        )
        assert (
            page.evaluate(
                "Chart.getChart('availChart').options.plugins.legend.labels.color"
            )
            == expected_color
        )
    assert len(download_rows(page)) == 26
    page.get_by_role("link", name="Terminal", exact=False).click()
    expect(page.locator("#price-outliers")).to_contain_text("2 high-price outliers")
    expect(page.locator("#stat-max")).to_have_text("€800.00")


@pytest.mark.parametrize("modern_name", ["dashboard.html", "index.html", "custom.html"])
def test_navigation_and_terminal_statistics(report_page, tmp_path, modern_name):
    products = [
        Product(name=f"Product {p}", price=p, source_url="https://example.test")
        for p in [0, 10]
    ]
    page = report_page
    url = render_pair(tmp_path, products, modern_name)
    page.goto(url)
    page.get_by_role("link", name="Terminal", exact=False).click()
    expect(page.locator("#t-price")).to_have_text("5.00")
    expect(page.locator("#stat-med")).to_have_text("€5.00")
    expect(page.locator("#t-stock")).to_have_text("0%")
    assert sum(json.loads(page.locator("#chart-data").text_content())["counts"]) == 2
    page.get_by_role("link", name="[ DASHBOARD ]", exact=True).click()
    expect(page).to_have_url(url)


def test_hostile_text_zero_price_and_immediate_export(report_page, tmp_path):
    name = '=1+1, "quoted" </script><script>window.pwned=true</script>'
    page = report_page
    page.goto(
        render_pair(
            tmp_path,
            [
                Product(
                    name=name,
                    price=0,
                    availability="Unknown",
                    source_url="https://example.test",
                )
            ],
        )
    )
    page.get_by_label("Search catalog").fill("quoted")
    page.get_by_label("Maximum price").fill("0")
    rows = download_rows(page)
    assert len(rows) == 1
    assert rows[0]["name"] == "'" + name
    assert float(rows[0]["price"]) == 0
    expect(page.locator("#grid-table tbody tr")).to_contain_text(name)
    assert page.evaluate("window.pwned === undefined")


def test_empty_reports_remain_navigable(report_page, tmp_path):
    page = report_page
    page.goto(render_pair(tmp_path, []))
    expect(page.locator("#catalog-match-count")).to_have_text("0 matching products")
    assert download_rows(page) == []
    page.get_by_role("link", name="Terminal", exact=False).click()
    expect(page.locator("#t-count")).to_have_text("0")
    expect(page.locator("#stat-med")).to_have_text("—")


def test_missing_prices_are_distinct_from_free_products(report_page, tmp_path):
    products = [
        Product(name=name, price=price, source_url="https://fixture.test")
        for name, price in [
            ("Unknown price", None),
            ("Free product", 0),
            ("Paid product", 10),
        ]
    ]
    page = report_page
    page.goto(render_pair(tmp_path, products))
    expect(page.locator("#kpi-avg")).to_have_text("5.00")
    expect(page.locator("#grid-table tbody")).to_contain_text("Price unavailable")
    exported = download_rows(page)
    assert next(p for p in exported if p["name"] == "Unknown price")["price"] == ""
    page.get_by_label("Maximum price").fill("0")
    expect(page.locator("#catalog-match-count")).to_have_text("1 matching products")
    assert [p["name"] for p in download_rows(page)] == ["Free product"]
    page.get_by_role("button", name="Reset", exact=True).click()
    page.get_by_label("Search catalog").fill("price unavailable")
    assert [p["name"] for p in download_rows(page)] == ["Unknown price"]
    page.get_by_role("link", name="Terminal", exact=False).click()
    expect(page.locator("#t-price")).to_have_text("5.00")
    expect(page.locator("#stat-med")).to_have_text("€5.00")
