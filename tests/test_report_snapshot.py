"""Regressions for catalog scope, statistics and report navigation."""

import csv
import json
from unittest.mock import patch
from urllib.parse import unquote

from bs4 import BeautifulSoup
import pytest
from typer.testing import CliRunner

from main import app, _generate_pipeline_dashboards
from models import Product
from scraper.results import PageResult, ScrapeRunResult
from visualization.report_data import ReportSnapshot


def embedded(html, element_id):
    return json.loads(BeautifulSoup(html, "html.parser").find(id=element_id).string)


@pytest.mark.parametrize(
    "prices, average, median",
    [
        ([], None, None),
        ([0], 0, 0),
        ([0, 10], 5, 5),
        ([10, 20], 15, 15),
        ([10, 40], 25, 25),
        ([10.25, 40.25], 25.25, 25.25),
        ([0, 10, 20], 10, 10),
        ([9.99, 9.99], 9.99, 9.99),
    ],
)
def test_price_statistics(prices, average, median):
    products = [
        Product(name=f"Product {i}", price=p, source_url="https://example.test")
        for i, p in enumerate(prices)
    ]
    context = ReportSnapshot.from_products(products).context
    assert context["statistics"]["average"] == (
        pytest.approx(average) if average is not None else None
    )
    assert context["statistics"]["median"] == (
        pytest.approx(median) if median is not None else None
    )
    assert sum(context["chart_data"]["counts"]) == len(prices)


def test_histogram_boundaries_count_each_product_once():
    products = [
        Product(name=f"Product {price}", price=price, source_url="https://example.test")
        for price in range(0, 41, 5)
    ]
    chart = ReportSnapshot.from_products(products).context["chart_data"]
    assert chart["counts"] == [1, 1, 1, 1, 1, 1, 1, 2]
    assert chart["labels"][-1] == "35-40"


@pytest.mark.parametrize(
    "modern_name, terminal_name",
    [
        ("data/dashboard.html", "data/dashboard_terminal.html"),
        ("docs/index.html", "docs/dashboard_terminal.html"),
        ("custom reports/catalog #1.html", "other reports/terminal & view.html"),
    ],
)
def test_reports_share_data_and_resolve_sibling_links(
    tmp_path, db_manager, sample_products, modern_name, terminal_name
):
    db_manager.save_products(sample_products)
    modern = tmp_path / modern_name
    terminal = tmp_path / terminal_name
    with patch.object(
        db_manager, "get_catalog_snapshot", wraps=db_manager.get_catalog_snapshot
    ) as read:
        _generate_pipeline_dashboards(db_manager, str(modern), str(terminal))
        read.assert_called_once_with()
    for key in ("products-data", "statistics-data", "chart-data", "report-metadata"):
        assert embedded(modern.read_text(encoding="utf-8"), key) == embedded(
            terminal.read_text(encoding="utf-8"), key
        )
    for origin, destination in ((modern, terminal), (terminal, modern)):
        links = BeautifulSoup(
            origin.read_text(encoding="utf-8"), "html.parser"
        ).find_all("a", href=True)
        assert any(
            (origin.parent / unquote(link["href"])).resolve() == destination.resolve()
            for link in links
        )


@pytest.mark.parametrize("empty_run", [False, True])
def test_cli_reports_persisted_catalog_across_repeated_runs(
    tmp_path, db_manager, empty_run
):
    """An old stored product survives a new or empty run in both reports."""
    db_manager.save_products(
        [Product(name="Existing", price=10, source_url="https://example.test")]
    )
    modern = tmp_path / "dashboard.html"
    terminal = tmp_path / "dashboard_terminal.html"
    csv_path = tmp_path / "catalog.csv"
    export = db_manager.export_for_powerbi
    with (
        patch("main.DatabaseManager", return_value=db_manager),
        patch.object(db_manager, "close"),
        patch("main.DATA_DIR", tmp_path),
        patch("main.BrowserScraper") as browser,
        patch("main.DASHBOARD_HTML_PATH", modern),
        patch("main.TERMINAL_DASHBOARD_HTML_PATH", terminal),
        patch.object(
            db_manager, "export_for_powerbi", side_effect=lambda: export(str(csv_path))
        ),
    ):

        def collection(**kwargs):
            products = (
                []
                if empty_run
                else [
                    Product(
                        name="New free product",
                        price=0,
                        source_id="new",
                        availability="In Stock",
                        source_url="https://example.test",
                    )
                ]
            )
            return ScrapeRunResult(
                "https://example.test",
                1,
                "browser",
                pages=[
                    PageResult(
                        1,
                        "https://example.test",
                        status="success" if products else "empty",
                        products=products,
                    )
                ],
            ).finish("page_limit")

        browser.return_value.scrape.side_effect = collection
        for _ in range(2):
            result = CliRunner().invoke(app, ["scrape", "--pages", "1"])
            assert result.exit_code == 0, result.output
    expected = {"Existing"} if empty_run else {"Existing", "New free product"}
    for path in (modern, terminal):
        products = embedded(path.read_text(encoding="utf-8"), "products-data")
        assert {p["name"] for p in products} == expected
        assert len(products) == len(expected)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        assert {row["name"] for row in csv.DictReader(stream)} == expected
