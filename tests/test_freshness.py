"""Observation age and stock evidence are independent in the report."""

from datetime import datetime, timedelta, timezone

import pandas as pd

from scrapingstore.report.columnar import decode_columnar
from scrapingstore.report.generator import generate_dashboard
from scrapingstore.report.snapshot import ReportSnapshot
from tests.test_history import product
from tests.test_report_snapshot import embedded
from visualization.report_data import _build_context, _normalize_products_df


def test_freshness_boundary_utc_future_and_missing_time():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        [
            {"name": "Boundary", "scraped_at": now - timedelta(days=7)},
            {"name": "Stale", "scraped_at": now - timedelta(days=7, seconds=1)},
            {"name": "Offset", "scraped_at": "2026-09-08T02:00:00+02:00"},
            {"name": "Missing", "scraped_at": None},
            {"name": "Future", "scraped_at": now + timedelta(seconds=1)},
        ]
    )
    context = _build_context(_normalize_products_df(frame), now)
    assert [p["freshness"] for p in context["products"]] == [
        "recent",
        "stale",
        "recent",
        "unknown",
        "future",
    ]
    assert context["freshness"]["recent"] == 2
    assert context["products"][3]["observed_age_days"] is None


def test_report_shows_stale_stock_without_changing_it(tmp_path):
    observed = product(scraped_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    snapshot = ReportSnapshot.from_products(
        [observed], generated_at=datetime(2026, 9, 8, tzinfo=timezone.utc)
    )
    assert snapshot.context["availability"]["in_stock"] == 1
    assert snapshot.context["freshness"]["stale"] == 1
    path = tmp_path / "report.html"
    generate_dashboard(snapshot, str(path))
    html = path.read_text(encoding="utf-8")
    row = decode_columnar(embedded(html, "columnar-data"))[0]
    assert row["availability"] == "In Stock"
    assert row["freshness"] == "stale"
    metadata = embedded(html, "report-metadata")
    assert metadata["freshness"]["stale"] == 1
    assert metadata["generated_at"].startswith("2026-09-08")
    timeline = embedded(html, "timeline-data")
    assert timeline["runs"][0]["started_at"].startswith("2026-08-01")
    assert timeline["rows"][0]["cells"][0][1] == "in"
    assert observed.availability == "In Stock"
