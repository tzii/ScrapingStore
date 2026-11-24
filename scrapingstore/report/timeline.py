"""Per-product price and stock timeline across archived runs, embedded in the HTML report.

Each row is one product (keyed by its stable source key) and each cell is one run.
Changes are only computed for products with a stable identity (native ID or product
URL) and a single currency. A price change measured against an earlier run because
the previous run had no readable price for the product (or did not see it) is kept,
but flagged as a gap change: the price moved, but the run it moved in is unknown.
Headline counts only include changes between the last two runs, matching
``compare_observations``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from scrapingstore.io_utils import as_utc

STRONG_IDENTITIES = ("native", "url")

# Cell layout (a list, to keep the embedded JSON small):
#   [0] price          float, or None when the product was seen but its price was unreadable
#   [1] stock          "in" | "out" | "unknown"
#   [2] price_change   "down" | "up" | "down_gap" | "up_gap" | ""
#   [3] stock_change   "back" | "out" | ""  (only against the immediately previous run)
#   [4] compared_with  index of the run whose price was compared, or None
PRICE, STOCK, PRICE_CHANGE, STOCK_CHANGE, COMPARED_WITH = range(5)


def _get(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return as_utc(value).isoformat().replace("+00:00", "Z")
    text = str(value).strip()
    if not text:
        return None
    try:
        norm = text[:-1] + "+00:00" if text.endswith("Z") else text
        return as_utc(datetime.fromisoformat(norm)).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _stock(value: Any) -> str:
    if value == "In Stock":
        return "in"
    if value == "Out of Stock":
        return "out"
    return "unknown"


def _cents(value: float) -> int:
    return round(value * 100)


def _run_entry(manifest: Mapping[str, Any], observations: Sequence[Any]) -> Dict[str, Any]:
    run_id = manifest.get("run_id")
    return {
        "id": run_id,
        "short_id": manifest.get("short_id") or (str(run_id)[:8] if run_id else None),
        "started_at": _iso(manifest.get("started_at")),
        "status": manifest.get("status") or "unknown",
        "degraded_reasons": list(manifest.get("degraded_reasons") or []),
        "observed": len(observations),
        "readable_prices": sum(1 for p in observations if _get(p, "price") is not None),
    }


def _columns(
    history: Optional[Sequence[Tuple[Mapping[str, Any], Sequence[Any]]]],
    catalog: Sequence[Any],
    run: Optional[Mapping[str, Any]],
) -> List[Tuple[Dict[str, Any], List[Any]]]:
    if history:
        return [(dict(manifest), list(products)) for manifest, products in history]
    if not catalog:
        return []
    manifest = dict(run or {})
    if not manifest.get("started_at"):
        stamps = [s for s in (_iso(_get(p, "scraped_at")) for p in catalog) if s]
        manifest["started_at"] = max(stamps) if stamps else None
    manifest.setdefault("status", "unknown")
    return [(manifest, list(catalog))]


def build_timeline(
    history: Optional[Sequence[Tuple[Mapping[str, Any], Sequence[Any]]]],
    catalog: Sequence[Any] = (),
    run: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the product x run timeline.

    ``history`` is the chronological list of ``(manifest, products)`` pairs. Without
    history, the catalog becomes a single column labelled with ``run`` (if given) or
    the newest observation time. Catalog products that no embedded run observed are
    kept as rows with empty cells so the report still lists them.
    """
    columns = _columns(history, catalog, run)
    runs = [_run_entry(manifest, observations) for manifest, observations in columns]
    n = len(columns)

    rows: Dict[str, Dict[str, Any]] = {}
    currencies: Dict[str, set] = {}
    for index, (_, observations) in enumerate(columns):
        for product in observations:
            key = _get(product, "source_key")
            if not key:
                continue
            row = rows.get(key)
            if row is None:
                row = rows[key] = {"key": key, "cells": [None] * n}
                currencies[key] = set()
            price = _get(product, "price")
            row["cells"][index] = [
                float(price) if price is not None else None,
                _stock(_get(product, "availability")),
                "",
                "",
                None,
            ]
            row["name"] = _get(product, "name") or ""
            row["category"] = _get(product, "category")
            row["url"] = _get(product, "product_url")
            row["currency"] = _get(product, "currency") or "EUR"
            row["identity"] = _get(product, "identity_kind") or "weak"
            if price is not None:
                currencies[key].add(row["currency"])

    for product in catalog:
        key = _get(product, "source_key")
        if not key or key in rows:
            continue
        rows[key] = {
            "key": key,
            "cells": [None] * n,
            "name": _get(product, "name") or "",
            "category": _get(product, "category"),
            "url": _get(product, "product_url"),
            "currency": _get(product, "currency") or "EUR",
            "identity": _get(product, "identity_kind") or "weak",
            "last_seen": _iso(_get(product, "scraped_at")),
        }
        currencies[key] = set()

    latest = n - 1
    summary = {
        "dropped": 0,
        "rose": 0,
        "dropped_gap": 0,
        "rose_gap": 0,
        "back_in_stock": 0,
        "sold_out": 0,
        "new": 0,
        "not_seen": 0,
    }
    for row in rows.values():
        cells = row["cells"]
        seen = [i for i, cell in enumerate(cells) if cell is not None]
        row["first"] = seen[0] if seen else None
        row["last"] = seen[-1] if seen else None
        row["mixed_currency"] = len(currencies[row["key"]]) > 1
        comparable = row["identity"] in STRONG_IDENTITIES
        row["comparable"] = comparable
        if not comparable:
            continue

        compare_prices = not row["mixed_currency"]
        last_priced: Optional[int] = None
        for i in seen:
            cell = cells[i]
            previous = cells[i - 1] if i > 0 else None
            if compare_prices and cell[PRICE] is not None and last_priced is not None:
                old = cells[last_priced][PRICE]
                if _cents(cell[PRICE]) != _cents(old):
                    direction = "down" if cell[PRICE] < old else "up"
                    cell[PRICE_CHANGE] = direction if last_priced == i - 1 else direction + "_gap"
                    cell[COMPARED_WITH] = last_priced
            if previous is not None:
                if previous[STOCK] == "out" and cell[STOCK] == "in":
                    cell[STOCK_CHANGE] = "back"
                elif previous[STOCK] == "in" and cell[STOCK] == "out":
                    cell[STOCK_CHANGE] = "out"
            if cell[PRICE] is not None:
                last_priced = i

        if latest < 1:
            continue
        now = cells[latest]
        if now is not None:
            change = now[PRICE_CHANGE]
            if change == "down":
                summary["dropped"] += 1
            elif change == "up":
                summary["rose"] += 1
            elif change == "down_gap":
                summary["dropped_gap"] += 1
            elif change == "up_gap":
                summary["rose_gap"] += 1
            if now[STOCK_CHANGE] == "back":
                summary["back_in_stock"] += 1
            elif now[STOCK_CHANGE] == "out":
                summary["sold_out"] += 1
            if row["first"] == latest:
                summary["new"] += 1
        elif cells[latest - 1] is not None:
            summary["not_seen"] += 1

    return {
        "runs": runs,
        "rows": list(rows.values()),
        "latest": summary if n >= 2 else None,
    }
