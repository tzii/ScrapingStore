"""Run inside an isolated wheel install outside the source repository."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import scrapingstore
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.ledger.models import Product


def cli(*args: str) -> str:
    return subprocess.run(
        ["scrapingstore", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def run() -> None:
    assert Path(scrapingstore.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    # Verify top-level site-packages namespace is NOT polluted by internal modules
    for forbidden in ("models", "database", "comparison"):
        assert importlib.util.find_spec(forbidden) is None, f"Namespace leak: {forbidden}"

    cli("--help")
    db = DatabaseManager()
    try:
        db.init_db()
        for run_id, price, ts in (
            ("old-run-001", 10.0, "2026-09-08T00:00:00Z"),
            ("new-run-002", 0.0, "2026-09-08T01:00:00Z"),
        ):
            db.save_collection(
                [
                    Product(
                        name="Wheel fixture",
                        source_url="https://fixture.test",
                        source_id="1",
                        price=price,
                        availability="In Stock",
                    )
                ],
                {
                    "run_id": run_id,
                    "started_at": ts,
                    "status": "complete",
                    "scope": {"description": "Offline wheel fixture"},
                    "products_accepted": 1,
                },
            )
    finally:
        db.close()

    assert "old-run" in cli("runs", "--plain")
    assert json.loads(cli("inspect-run", "old-run", "--products"))["products"][0]["price"] == 10.0
    assert (
        json.loads(cli("compare-runs", "@prev", "@latest"))["changes"][0]["changes"]["price"]["delta"]
        == -10.0
    )
    cli("export")
    cli("generate-report")
    cli("generate-report", "--docs", "--run-id", "old-run")
    for path in ("data/dashboard.html", "docs/index.html"):
        html = Path(path).read_text(encoding="utf-8")
        assert "Wheel fixture" in html and "timeline-data" in html
    assert not Path("data/dashboard_terminal.html").exists()
    assert Path("data/products_powerbi.csv").is_file()
    print("Clean wheel CLI, zero namespace pollution, ledger, diff, export, and report passed.")


if __name__ == "__main__":
    run()
