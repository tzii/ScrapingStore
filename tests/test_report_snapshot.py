"""Regressions for catalog scope, statistics, and the embedded report data."""

import csv
import json
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from typer.testing import CliRunner

from scrapingstore.cli.app import _generate_pipeline_dashboard, app
from scrapingstore.ledger.models import Product
from scrapingstore.report.columnar import decode_columnar
from scrapingstore.report.snapshot import ReportSnapshot
from scrapingstore.sources.results import PageResult, ScrapeRunResult


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
    assert chart["interval_labels"][0] == "[0,5)"
    assert chart["interval_labels"][-1] == "[35,40]"


@pytest.mark.parametrize(
    "report_name",
    ["data/dashboard.html", "docs/index.html", "custom reports/catalog #1.html"],
)
def test_pipeline_report_reads_the_catalog_once(
    tmp_path, db_manager, sample_products, report_name
):
    db_manager.save_products(sample_products)
    report = tmp_path / report_name
    with patch.object(
        db_manager, "get_catalog_snapshot", wraps=db_manager.get_catalog_snapshot
    ) as read:
        assert _generate_pipeline_dashboard(db_manager, str(report)) == str(report)
        read.assert_called_once_with()
    html = report.read_text(encoding="utf-8")
    for key in (
        "timeline-data",
        "columnar-data",
        "statistics-data",
        "report-metadata",
        "smells-data",
        "restock-data",
    ):
        assert BeautifulSoup(html, "html.parser").find(id=key) is not None
    names = {row["name"] for row in embedded(html, "timeline-data")["rows"]}
    assert names == {p.name for p in sample_products}


@pytest.mark.parametrize("empty_run", [False, True])
def test_cli_reports_persisted_catalog_across_repeated_runs(
    tmp_path, db_manager, empty_run, monkeypatch
):
    """An old stored product survives a new or empty run in the report."""
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    db_manager.save_products(
        [Product(name="Existing", price=10, source_url="https://example.test")]
    )
    report = tmp_path / "data" / "dashboard.html"
    csv_path = tmp_path / "data" / "products_powerbi.csv"
    export = db_manager.export_for_powerbi
    with (
        patch("scrapingstore.cli.app.DatabaseManager", return_value=db_manager),
        patch.object(db_manager, "close"),
        patch("scrapingstore.cli.app.AutoScraper") as auto_scraper,
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
                "static",
                pages=[
                    PageResult(
                        1,
                        "https://example.test",
                        status="success" if products else "empty",
                        products=products,
                    )
                ],
            ).finish("page_limit")

        auto_scraper.return_value.scrape.side_effect = collection
        for _ in range(2):
            result = CliRunner().invoke(app, ["scrape", "--pages", "1"])
            assert result.exit_code == 0, result.output
    expected = {"Existing"} if empty_run else {"Existing", "New free product"}
    products = decode_columnar(embedded(report.read_text(encoding="utf-8"), "columnar-data"))
    assert {p["name"] for p in products} == expected
    assert len(products) == len(expected)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        assert {row["name"] for row in csv.DictReader(stream)} == expected
