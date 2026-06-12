import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from config import DASHBOARD_HTML_PATH, TEMPLATES_DIR
from database import DatabaseManager
from logger import get_logger

logger = get_logger(__name__)

_PRODUCT_COLUMNS = (
    "name",
    "price",
    "availability",
    "image_url",
    "scraped_at",
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
        "price": 0.0,
        "availability": "Unknown",
        "image_url": None,
        "scraped_at": None,
    }
    for column, default in defaults.items():
        if column not in normalized.columns:
            normalized[column] = default

    normalized["name"] = normalized["name"].fillna("").astype(str)
    normalized["price"] = (
        pd.to_numeric(normalized["price"], errors="coerce")
        .replace([float("inf"), float("-inf")], 0.0)
        .fillna(0.0)
        .clip(lower=0.0)
    )
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
    top = df.sort_values("price", ascending=False).head(n)
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
    """Build compact histogram labels and counts for Chart.js."""
    if prices.empty:
        return {"labels": ["No Data"], "counts": [0]}

    min_price = int(prices.min())
    max_price = int(prices.max())
    if max_price == min_price:
        return {"labels": [f"{min_price}-{min_price + 10}"], "counts": [len(prices)]}

    step = max(5, (max_price - min_price) // 8)
    if step > 10:
        step = (step // 10) * 10

    labels: List[str] = []
    counts: List[int] = []
    for start in range(min_price, max_price + step, step):
        end = start + step
        count = int(((prices >= start) & (prices < end)).sum())
        if count:
            labels.append(f"{start}-{end}")
            counts.append(count)
    return {"labels": labels, "counts": counts}


def _build_context(df: pd.DataFrame) -> Dict[str, Any]:
    """Build the complete template context from normalized product data."""
    total_products = len(df)
    prices = df["price"]
    average_price = float(prices.mean()) if total_products else 0.0
    min_price = float(prices.min()) if total_products else 0.0
    max_price = float(prices.max()) if total_products else 0.0
    availability, availability_pct, availability_label = _availability_stats(df)
    generated_at = datetime.now().astimezone()

    return {
        "timestamp": generated_at.strftime("%b %d, %Y • %H:%M"),
        "generated_iso": generated_at.isoformat(timespec="seconds"),
        "products": _json_records(df[list(_PRODUCT_COLUMNS)]),
        "franchises": _detect_franchises(df),
        "top_products": _top_products(df),
        "kpi": {
            "total": total_products,
            "avg": f"{average_price:.2f}",
            "premium": int((prices > 85).sum()),
            "avail_pct": availability_pct,
        },
        "kpi_min": f"{min_price:.2f}",
        "kpi_max": f"{max_price:.2f}",
        "kpi_availability_label": availability_label,
        "chart_data": _price_histogram(prices),
        "availability": availability,
    }


def generate_dashboard(db: DatabaseManager, output_path: Optional[str] = None) -> str:
    """Generate the modern HTML dashboard."""
    logger.info("Generating dashboard...")
    df = _normalize_products_df(db.get_products_df())

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("dashboard_modern_template.html")
    html_content = template.render(_build_context(df))

    destination = Path(output_path) if output_path else DASHBOARD_HTML_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_content, encoding="utf-8")

    logger.info(f"Dashboard saved to {destination}")
    return str(destination)
