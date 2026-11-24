"""Rebuild the GitHub Pages report in docs/ from the simulated store.

Run from repository root:
    python -m scripts.refresh_demo
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scrapingstore.cli.app import _persist_collection
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.report.generator import generate_dashboard
from scrapingstore.report.snapshot import ReportSnapshot
from scrapingstore.sources.mock_market import MockMarket

SCOPE = "Simulated store (scrapingstore demo)"


def run() -> None:
    report = Path("docs/index.html")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = DatabaseManager(f"sqlite:///{tmp_path / 'demo.db'}")
        try:
            db.init_db()
            market = MockMarket(seed=42, sku_count=96, per_page=24)
            for ep in range(5):
                run_res = market.collect_epoch(ep)
                _persist_collection(db, run_res, data_dir=tmp_path, archive_html=True)
            products, latest = db.get_catalog_snapshot()
            history = db.get_multi_run_history(limit=5)
            snapshot = ReportSnapshot.from_products(
                products, run=latest, scope=SCOPE, history=history
            )
            generate_dashboard(snapshot, str(report))
        finally:
            db.close()
    print(f"Rebuilt {report} ({report.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    run()
