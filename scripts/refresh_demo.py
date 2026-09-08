"""Refresh the checked-in archived showcase with current templates, without scraping.

Run from the repository root: python -m scripts.refresh_demo
The embedded observations keep their original times. Legacy zeros have no known
meaning, so follow the database migration's unknown-price policy.
"""

import json
from pathlib import Path

from bs4 import BeautifulSoup

from models import Product
from visualization.dashboard_generator import generate_dashboard
from visualization.report_data import ReportSnapshot
from visualization.terminal_dashboard_generator import generate_terminal_dashboard


def run():
    modern = Path("docs/index.html")
    terminal = Path("docs/dashboard_terminal.html")
    document = BeautifulSoup(modern.read_text(encoding="utf-8"), "html.parser")
    records = json.loads(document.find("script", id="products-data").string)
    products = []
    for index, record in enumerate(records):
        if "source_key" not in record:
            record.update(
                source_key=f"legacy:demo:{index}",
                identity_kind="legacy",
                parser_version="legacy",
                source_url="https://sandbox.oxylabs.io/products",
            )
            if not record.get("price"):
                record.update(price=None, price_status="legacy_unknown")
        products.append(Product.model_validate(record))
    snapshot = ReportSnapshot.from_products(
        products, scope="Archived showcase snapshot (collection outcome not recorded)"
    )
    generate_dashboard(snapshot, str(modern), terminal_path=str(terminal))
    generate_terminal_dashboard(snapshot, str(terminal), dashboard_path=str(modern))
    for destination in (modern, terminal):
        destination.write_text(
            "\n".join(
                line.rstrip()
                for line in destination.read_text(encoding="utf-8").splitlines()
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        f"Refreshed {len(products)} archived observations; collection times preserved."
    )


if __name__ == "__main__":
    run()
