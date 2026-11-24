"""Exercise saved-run inspection, short IDs, and report replay through the public CLI."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from scrapingstore.cli.app import _persist_collection, app
from scrapingstore.ledger.models import Product
from scrapingstore.report.columnar import decode_columnar
from scrapingstore.sources.results import PageResult, ScrapeRunResult
from tests.test_report_snapshot import embedded


def collection(name="Original", price=12, day=1, empty=False):
    products = (
        []
        if empty
        else [
            Product(
                name=name,
                price=price,
                price_raw="12,00 €" if price == 12 else None,
                source_id="same",
                source_url="https://source.test/products",
                scraped_at=datetime(2026, 9, day, tzinfo=timezone.utc),
            )
        ]
    )
    run = ScrapeRunResult(
        "https://source.test/products",
        1,
        "static",
        started_at=datetime(2026, 9, day, tzinfo=timezone.utc),
        pages=[
            PageResult(
                1,
                "https://source.test/products",
                status="empty" if empty else "success",
                products=products,
            )
        ],
    ).finish("page_limit")
    return run


def persist(db, run, tmp_path):
    _persist_collection(db, run, data_dir=tmp_path)


def invoke(db, args):
    with (
        patch("scrapingstore.cli.app.DatabaseManager", return_value=db),
        patch.object(db, "close"),
    ):
        return CliRunner().invoke(app, args)


def test_list_and_inspect_original_observations_after_catalog_update(
    db_manager, tmp_path
):
    first = collection()
    newer = collection(name="Renamed", price=None, day=2)
    persist(db_manager, first, tmp_path)
    persist(db_manager, newer, tmp_path)

    result = invoke(db_manager, ["runs", "--limit", "1", "--plain"])
    assert result.exit_code == 0, result.output
    assert newer.run_id in result.output and first.run_id not in result.output
    assert "complete" in result.output and "1 products" in result.output

    result = invoke(db_manager, ["inspect-run", first.run_id, "--products"])
    assert result.exit_code == 0, result.output
    evidence = json.loads(result.stdout)
    assert evidence["run"]["products_accepted"] == 1
    assert evidence["run"]["history_version"] == 1
    assert evidence["products"][0]["name"] == "Original"
    assert evidence["products"][0]["price"] == 12
    assert evidence["products"][0]["price_raw"] == "12,00 €"
    assert evidence["products"][0]["last_run_id"] == first.run_id
    assert db_manager.get_all_products()[0].name == "Renamed"
    sidecar = json.loads((tmp_path / "runs" / f"{first.run_id}.json").read_text())
    assert sidecar == evidence["run"]


@pytest.mark.parametrize("empty", [False, True])
def test_report_selected_run_uses_archived_data_and_metadata(
    db_manager, tmp_path, empty, monkeypatch
):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    first = collection(empty=empty)
    persist(db_manager, first, tmp_path)
    persist(db_manager, collection(name="Later", price=99, day=2), tmp_path)
    report = tmp_path / "data" / "dashboard.html"
    result = invoke(db_manager, ["generate-report", "--run-id", first.run_id])
    assert result.exit_code == 0, result.output
    html = report.read_text(encoding="utf-8")
    products = decode_columnar(embedded(html, "columnar-data"))
    assert [p["name"] for p in products] == ([] if empty else ["Original"])
    metadata = embedded(html, "report-metadata")
    assert metadata["scope"] == f"Collection run {first.run_id}"
    assert metadata["collection_label"] == "Selected collection"
    assert metadata["latest_collection"]["run_id"] == first.run_id
    timeline = embedded(html, "timeline-data")
    assert [run["id"] for run in timeline["runs"]] == ([] if empty else [first.run_id])
    assert [row["name"] for row in timeline["rows"]] == ([] if empty else ["Original"])
    if products:
        assert products[0]["scraped_at"].startswith("2026-09-01")
        assert products[0]["parser_version"] == "3.0"


def test_legacy_manifest_remains_inspectable_but_cannot_fake_empty_history(
    db_manager, tmp_path, monkeypatch
):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    legacy = collection().manifest()
    db_manager.save_run(legacy)
    result = invoke(db_manager, ["inspect-run", legacy["run_id"]])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["run"] == legacy
    output = tmp_path / "data" / "dashboard.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("Existing report", encoding="utf-8")
    for args in (
        ["inspect-run", legacy["run_id"], "--products"],
        ["generate-report", "--run-id", legacy["run_id"]],
    ):
        result = invoke(db_manager, args)
        assert result.exit_code == 1
        assert "no supported observation history" in result.output
        assert output.read_text() == "Existing report"


def test_missing_run_and_empty_run_list_are_clear(db_manager):
    result = invoke(db_manager, ["runs"])
    assert result.exit_code == 0 and "No saved collections" in result.output
    for args in (
        ["inspect-run", "missing"],
        ["generate-report", "--run-id", "missing"],
    ):
        result = invoke(db_manager, args)
        assert result.exit_code == 1 and "not found" in result.output


def test_unexpected_collector_error_retains_completed_evidence(
    db_manager, tmp_path, monkeypatch
):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    run = collection()
    run.finished_at = None
    run.stop_reason = "running"
    with patch("scrapingstore.cli.app._create_scraper") as factory:
        factory.return_value.last_run = run
        factory.return_value.scrape.side_effect = RuntimeError("Unexpected error")
        result = invoke(db_manager, ["scrape", "--no-export", "--no-dashboard"])
    assert result.exit_code == 2, result.output
    evidence = db_manager.get_run(run.run_id)
    assert evidence["status"] == "partial"
    assert evidence["stop_reason"] == "collector_error"
    assert any("Unexpected error" in error for error in evidence["errors"])
    assert db_manager.get_run_products(run.run_id)[0].name == "Original"


def test_failed_persistence_does_not_claim_saved_products(
    db_manager, tmp_path, monkeypatch
):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    run = collection()
    with (
        patch("scrapingstore.cli.app._create_scraper") as factory,
        patch.object(
            db_manager, "save_collection", side_effect=RuntimeError("Write failed")
        ),
    ):
        factory.return_value.scrape.return_value = run
        result = invoke(db_manager, ["scrape", "--no-export", "--no-dashboard"])
    assert result.exit_code == 1
    sidecar = json.loads((tmp_path / "data" / "runs" / f"{run.run_id}.json").read_text())
    assert sidecar["products_accepted"] == 0
    assert "history_version" not in sidecar
    assert db_manager.get_run(run.run_id) is None


def test_conflicting_retry_keeps_original_sidecar_and_records_failure(
    db_manager, tmp_path, monkeypatch
):
    monkeypatch.setenv("SCRAPINGSTORE_HOME", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    data_dir = tmp_path / "data"
    original = collection()
    persist(db_manager, original, data_dir)
    original_path = data_dir / "runs" / f"{original.run_id}.json"
    original_bytes = original_path.read_bytes()
    attempted = collection(name="Conflicting retry", price=99)
    attempted.run_id = original.run_id
    with patch("scrapingstore.cli.app._create_scraper") as factory:
        factory.return_value.scrape.return_value = attempted
        result = invoke(db_manager, ["scrape", "--no-export", "--no-dashboard"])
    assert result.exit_code == 1, result.output
    assert original_path.read_bytes() == original_bytes
    assert db_manager.get_run_products(original.run_id)[0].name == "Original"
    attempts = list((data_dir / "runs").glob(f"{original.run_id}.attempt-*.json"))
    assert len(attempts) == 1
    failure = json.loads(attempts[0].read_text())
    assert failure["products_accepted"] == 0
    assert any("immutable" in error for error in failure["errors"])
