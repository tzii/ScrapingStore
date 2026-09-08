"""Run with a clean wheel environment, outside the repository working directory."""

import json
import subprocess
import sys
from pathlib import Path

import main
from database import DatabaseManager
from models import Product


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "main", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run():
    assert Path(main.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    subprocess.run(["scrapingstore", "--help"], check=True, capture_output=True)
    db = DatabaseManager()
    try:
        db.init_db()
        for run_id, price in (("old", 10), ("new", 0)):
            db.save_collection(
                [
                    Product(
                        name="Wheel fixture",
                        source_url="https://fixture.test",
                        source_id="1",
                        price=price,
                    )
                ],
                {
                    "run_id": run_id,
                    "started_at": "2026-09-08T00:00:00Z",
                    "status": "complete",
                    "scope": {"description": "Offline wheel fixture"},
                    "products_accepted": 1,
                },
            )
    finally:
        db.close()
    assert "old" in cli("runs")
    assert (
        json.loads(cli("inspect-run", "old", "--products"))["products"][0]["price"]
        == 10
    )
    assert (
        json.loads(cli("compare-runs", "old", "new"))["changes"][0]["changes"]["price"][
            "delta"
        ]
        == -10
    )
    cli("export")
    cli("generate-report")
    cli("generate-report", "--docs", "--run-id", "old")
    for path in (
        "data/dashboard.html",
        "data/dashboard_terminal.html",
        "docs/index.html",
        "docs/dashboard_terminal.html",
    ):
        html = Path(path).read_text(encoding="utf-8")
        assert "Wheel fixture" in html and "report-metadata" in html
    assert Path("data/products_powerbi.csv").is_file()
    print(
        "Clean wheel CLI, history, comparison, export and both report templates passed."
    )


if __name__ == "__main__":
    run()
