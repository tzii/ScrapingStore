"""Outlier accounting and collection dates must remain honest in summaries."""

from datetime import datetime, timezone

import pandas as pd

from models import Product
from visualization.report_data import (
    ReportSnapshot,
    _build_context,
    _normalize_products_df,
)


def test_separate_outliers_preserve_all_prices_and_empty_bins():
    prices = [50, 55, 60, 65, 70, 75, 80, 85] * 3 + [0, 500, 800, None]
    products = [
        Product(name=f"Product {i}", price=p, source_url="https://example.test")
        for i, p in enumerate(prices)
    ]
    products.append(
        Product(
            name="Other currency",
            price=2000,
            currency="USD",
            source_url="https://example.test",
        )
    )
    context = ReportSnapshot.from_products(products).context
    chart = context["chart_data"]
    assert chart["outlier_count"] == 2
    assert sum(chart["counts"]) == chart["main_count"] == 25
    assert chart["main_count"] + chart["outlier_count"] == chart["total"] == 27
    assert 0 in chart["counts"]
    assert context["statistics"]["maximum"] == 800
    assert context["kpi"]["median"] == "70.00"
    assert [p["price"] for p in context["price_outliers"]] == [800, 500]


def test_constant_prices_keep_exact_threshold_in_main_range():
    products = [
        Product(name=str(i), price=p, source_url="https://example.test")
        for i, p in enumerate([10] * 8 + [100])
    ]
    chart = ReportSnapshot.from_products(products).context["chart_data"]
    assert chart["outlier_threshold"] == 10
    assert chart["main_count"] == 8 and chart["outlier_count"] == 1


def test_observation_dates_are_utc_and_independent_of_generation():
    products = [
        Product(
            name="First",
            source_url="https://example.test",
            scraped_at=datetime.fromisoformat("2025-12-12T01:00:00+02:00"),
        ),
        Product(
            name="Last",
            source_url="https://example.test",
            scraped_at=datetime.fromisoformat("2025-12-13T00:00:00+00:00"),
        ),
    ]
    context = ReportSnapshot.from_products(
        products, generated_at=datetime(2026, 9, 8, tzinfo=timezone.utc)
    ).context
    assert (
        context["observation_period"]["label"]
        == "Data collected 11 December 2025 – 13 December 2025"
    )
    assert context["generated_iso"].startswith("2026-09-08")
    assert (
        ReportSnapshot.from_products([]).context["observation_period"]["label"]
        == "No observations yet"
    )


def test_missing_dates_are_not_replaced_by_generation_time():
    frame = _normalize_products_df(pd.DataFrame([{"name": "Undated"}]))
    period = _build_context(frame)["observation_period"]
    assert period == {
        "label": "Collection dates unavailable",
        "start": None,
        "end": None,
        "missing": 1,
    }
