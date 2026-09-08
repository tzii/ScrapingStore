import json
from collections import Counter
from dataclasses import dataclass
from math import ceil, floor
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from models import Product

_PRODUCT_COLUMNS = (
    "name",
    "price",
    "availability",
    "image_url",
    "scraped_at",
    "currency",
    "price_raw",
    "price_status",
    "source_key",
    "identity_kind",
    "product_url",
    "availability_raw",
    "availability_reason",
    "last_run_id",
    "source_url",
    "source_id",
    "parser_version",
)

# Common words to exclude when auto-detecting franchises
_STOP_WORDS = {
    "the",
    "of",
    "and",
    "a",
    "in",
    "for",
    "to",
    "is",
    "on",
    "at",
    "by",
    "an",
    "it",
    "with",
    "from",
    "edition",
    "game",
    "video",
    "-",
    "&",
    ":",
    "new",
    "pro",
    "set",
    "kit",
}


def _normalize_products_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return dashboard-ready product data with stable columns and values."""
    normalized = df.copy()
    defaults: Dict[str, Any] = {
        "name": "",
        "price": None,
        "availability": "Unknown",
        "image_url": None,
        "scraped_at": None,
        "currency": "EUR",
        "price_raw": None,
        "price_status": "missing",
        "source_key": None,
        "identity_kind": "weak",
        "product_url": None,
        "availability_raw": None,
        "availability_reason": None,
        "last_run_id": None,
        "source_url": None,
        "source_id": None,
        "parser_version": None,
    }
    for column, default in defaults.items():
        if column not in normalized.columns:
            normalized[column] = default

    normalized["name"] = normalized["name"].fillna("").astype(str)
    normalized["price"] = pd.to_numeric(normalized["price"], errors="coerce").replace(
        [float("inf"), float("-inf")], float("nan")
    )
    normalized["price"] = normalized["price"].where(normalized["price"] >= 0)
    normalized["availability"] = (
        normalized["availability"].fillna("Unknown").astype(str)
    )
    return normalized


def _detect_franchises(df: pd.DataFrame, top_n: int = 8) -> List[Dict[str, Any]]:
    """
    Auto-detect product franchises by finding the most common
    significant words across all product names.
    """
    word_counts: Counter[str] = Counter()
    for name in df["name"].dropna():
        for word in name.split():
            cleaned = word.strip("()[]{}:,.-!?").title()
            if len(cleaned) >= 3 and cleaned.lower() not in _STOP_WORDS:
                word_counts[cleaned] += 1

    return [
        {"name": word, "count": count}
        for word, count in word_counts.most_common(top_n)
        if count > 1
    ]


def _top_products(df: pd.DataFrame, n: int = 10) -> List[Dict[str, Any]]:
    """Return the n most expensive products for the insights panel."""
    top = (
        df[df["currency"].eq("EUR")]
        .dropna(subset=["price"])
        .sort_values("price", ascending=False)
        .head(n)
    )
    return _json_records(top[["name", "price", "availability"]])


def _json_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert a DataFrame into browser-safe, JSON-compatible records."""
    payload = df.to_json(orient="records", date_format="iso")
    records = json.loads(payload)
    return list(records)


def _availability_stats(df: pd.DataFrame) -> Tuple[Dict[str, int], str, str]:
    """Calculate availability counts, percentage, and health label."""
    total = len(df)
    statuses = df["availability"].str.strip().str.casefold()
    in_stock = int((statuses == "in stock").sum())
    out_of_stock = int((statuses == "out of stock").sum())
    unknown = max(total - in_stock - out_of_stock, 0)

    if total == 0:
        return (
            {"in_stock": 0, "out_of_stock": 0, "unknown": 0},
            "0%",
            "No Data",
        )

    percentage = (in_stock / total) * 100
    if percentage > 80:
        label = "Stock Level Healthy"
    elif percentage > 50:
        label = "Stock Level Moderate"
    else:
        label = "Stock Level Low"

    counts = {
        "in_stock": in_stock,
        "out_of_stock": out_of_stock,
        "unknown": unknown,
    }
    return counts, f"{int(percentage)}%", label


def _price_histogram(prices: pd.Series) -> Dict[str, List[Any]]:
    """Count each price once; the final bin includes its upper boundary."""
    if prices.empty:
        return {"labels": ["No Data"], "counts": [0]}

    min_price = floor(prices.min())
    max_price = float(prices.max())
    bin_count = 8
    step = max(5, ceil((max_price - min_price) / bin_count))

    labels: List[str] = []
    counts: List[int] = []
    for index in range(bin_count):
        start = min_price + index * step
        end = start + step
        upper = prices <= end if index == bin_count - 1 else prices < end
        count = int(((prices >= start) & upper).sum())
        if count:
            labels.append(f"{start}-{end}")
            counts.append(count)
    return {"labels": labels, "counts": counts}


def _build_context(df: pd.DataFrame) -> Dict[str, Any]:
    """Build the complete template context from normalized product data."""
    total_products = len(df)
    prices = df.loc[df["currency"].eq("EUR"), "price"].dropna()
    price_count = len(prices)
    average_price = float(prices.mean()) if price_count else None
    min_price = float(prices.min()) if price_count else None
    max_price = float(prices.max()) if price_count else None
    availability, availability_pct, availability_label = _availability_stats(df)
    generated_at = datetime.now().astimezone()

    return {
        "timestamp": generated_at.strftime("%b %d, %Y • %H:%M"),
        "generated_iso": generated_at.isoformat(timespec="seconds"),
        "scope": "Current stored catalog",
        "products": _json_records(df[list(_PRODUCT_COLUMNS)]),
        "franchises": _detect_franchises(df),
        "top_products": _top_products(df),
        "kpi": {
            "total": total_products,
            "avg": f"{average_price:.2f}" if average_price is not None else "—",
            "known_prices": price_count,
            "missing_prices": int(df["price"].isna().sum()),
            "premium": int((prices > 85).sum()),
            "avail_pct": availability_pct,
        },
        "kpi_min": f"{min_price:.2f}" if min_price is not None else "—",
        "kpi_max": f"{max_price:.2f}" if max_price is not None else "—",
        "kpi_availability_label": availability_label,
        "chart_data": _price_histogram(prices),
        "availability": availability,
        "statistics": {
            "total": total_products,
            "average": average_price,
            "minimum": min_price,
            "maximum": max_price,
            "median": float(prices.median()) if price_count else None,
            "std_dev": float(prices.std(ddof=0)) if price_count else None,
            "known_prices": price_count,
            "missing_prices": int(df["price"].isna().sum()),
        },
    }


@dataclass(frozen=True)
class ReportSnapshot:
    """One catalog selection, generation time and set of statistics for both views."""

    context: Dict[str, Any]

    @classmethod
    def from_products(
        cls,
        products: List[Product],
        run: Optional[Dict[str, Any]] = None,
        *,
        scope: str = "Current stored catalog",
        collection_label: str = "Latest collection",
    ) -> "ReportSnapshot":
        frame = pd.DataFrame([product.model_dump() for product in products])
        context = _build_context(_normalize_products_df(frame))
        context["last_run"] = run
        context["scope"] = scope
        context["collection_label"] = collection_label
        return cls(context)


def report_link(destination: Path, sibling: Path) -> str:
    """Build a browser link relative to the report, including custom filenames."""
    from urllib.parse import quote

    relative = os.path.relpath(sibling.resolve(), destination.resolve().parent)
    return quote(Path(relative).as_posix(), safe="/")
