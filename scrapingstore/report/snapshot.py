"""Report snapshot: catalog statistics, data checks, and the product x run timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scrapingstore import __version__
from scrapingstore.analytics.comparison import compare_observations
from scrapingstore.analytics.insights import (
    availability_stats,
    censored_restock_analysis,
    detect_franchises_tfidf,
    detect_possibly_delisted,
    genre_breakdown,
    observation_period,
    price_histogram,
    price_ladder,
    price_statistics,
)
from scrapingstore.io_utils import as_utc
from scrapingstore.ledger.models import Product
from scrapingstore.quality.gates import field_coverage
from scrapingstore.quality.smells import detect_smells
from scrapingstore.report.columnar import encode_columnar
from scrapingstore.report.timeline import build_timeline

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
    "category",
    "rating",
)


def _normalize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one product dict into browser-safe JSON-compatible primitives."""
    price = raw.get("price")
    if price is not None:
        try:
            price = float(price)
            if price < 0 or price != price or price in (float("inf"), float("-inf")):
                price = None
        except (TypeError, ValueError):
            price = None

    scraped = raw.get("scraped_at")
    scraped_iso: Optional[str] = None
    if isinstance(scraped, datetime):
        scraped_iso = as_utc(scraped).isoformat().replace("+00:00", "Z")
    elif scraped is not None and str(scraped).strip():
        text = str(scraped).strip()
        try:
            norm = text[:-1] + "+00:00" if text.endswith("Z") else text
            scraped_iso = as_utc(datetime.fromisoformat(norm)).isoformat().replace(
                "+00:00", "Z"
            )
        except ValueError:
            scraped_iso = None

    rating = raw.get("rating")
    if rating is not None:
        try:
            rating = float(rating)
            if rating != rating:
                rating = None
        except (TypeError, ValueError):
            rating = None

    return {
        "name": str(raw.get("name") or ""),
        "price": price,
        "availability": str(raw.get("availability") or "Unknown"),
        "image_url": raw.get("image_url"),
        "scraped_at": scraped_iso,
        "currency": str(raw.get("currency") or "EUR"),
        "price_raw": raw.get("price_raw"),
        "price_status": str(
            raw.get("price_status") or ("known" if price is not None else "missing")
        ),
        "source_key": raw.get("source_key"),
        "identity_kind": str(raw.get("identity_kind") or "weak"),
        "product_url": raw.get("product_url"),
        "availability_raw": raw.get("availability_raw"),
        "availability_reason": raw.get("availability_reason"),
        "last_run_id": raw.get("last_run_id"),
        "source_url": raw.get("source_url"),
        "source_id": raw.get("source_id"),
        "parser_version": raw.get("parser_version"),
        "category": raw.get("category"),
        "rating": rating,
    }


def _compute_freshness(
    products: List[Dict[str, Any]], generated_at: datetime
) -> Dict[str, Any]:
    """Attach UTC observation age metadata at report-generation time without altering stock."""
    counts = {"recent": 0, "stale": 0, "unknown": 0, "future": 0}
    for product in products:
        raw_ts = product.get("scraped_at")
        age: Optional[float] = None
        if raw_ts:
            try:
                norm = raw_ts[:-1] + "+00:00" if raw_ts.endswith("Z") else raw_ts
                observed = as_utc(datetime.fromisoformat(norm))
                age = (generated_at - observed).total_seconds()
            except ValueError:
                age = None
        if age is None:
            status, label = "unknown", "Time not recorded"
        elif age < 0:
            status, label = "future", "Observation after report time"
        elif age <= 7 * 86400:
            status, label = "recent", "Observed within 7 days"
        else:
            status, label = "stale", "Observed over 7 days ago"
        product["freshness"] = status
        product["freshness_label"] = label
        product["observed_age_days"] = None if age is None else round(age / 86400.0, 3)
        counts[status] += 1
    return {"threshold_days": 7, "as_of": generated_at.isoformat(), **counts}


def _top_products(products: Sequence[Dict[str, Any]], n: int = 10) -> List[Dict[str, Any]]:
    eur = [
        p
        for p in products
        if p.get("price") is not None and (p.get("currency") or "EUR") == "EUR"
    ]
    eur.sort(key=lambda p: (-float(p["price"]), p["name"]))
    return [
        {
            "name": p["name"],
            "price": p["price"],
            "availability": p["availability"],
            "source_key": p.get("source_key"),
            "category": p.get("category"),
        }
        for p in eur[:n]
    ]


def _build_context(
    raw_rows: Sequence[Dict[str, Any]],
    generated_at: Optional[datetime] = None,
    *,
    previous_prices: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    gen_at = as_utc(generated_at) if generated_at else datetime.now(timezone.utc)
    products = [_normalize_row(r) for r in raw_rows]
    freshness = _compute_freshness(products, gen_at)
    stats = price_statistics(products)
    chart = price_histogram(products)
    ladder = price_ladder(products)
    availability, availability_pct, availability_label = availability_stats(products)
    period = observation_period(products)
    franchises = detect_franchises_tfidf(products, top_n=10)
    genres = genre_breakdown(products, top_n=14)
    smells = [s.to_dict() for s in detect_smells(products, previous_prices=previous_prices)]

    high_prices: List[Dict[str, Any]] = []
    if chart["outlier_count"] and chart["outlier_threshold"] is not None:
        thresh = float(chart["outlier_threshold"])
        high_prices = [
            p
            for p in products
            if p.get("price") is not None
            and (p.get("currency") or "EUR") == "EUR"
            and float(p["price"]) > thresh
        ]

    # Health score: average fill rate across price, real image, and strong identity
    prod_models: List[Product] = []
    for p in products:
        if p["name"].strip():
            try:
                prod_models.append(
                    Product(
                        name=p["name"],
                        price=p["price"],
                        availability=p["availability"],
                        image_url=p["image_url"],
                        source_url=p["source_url"] or "https://example.test",
                        source_id=p["source_id"],
                        product_url=p["product_url"],
                        identity_kind=p["identity_kind"],
                        category=p["category"],
                    )
                )
            except ValueError:
                pass
    coverage = field_coverage(prod_models)
    health_score = round(
        (
            coverage["known_price_rate"] * 0.45
            + coverage["real_image_rate"] * 0.25
            + coverage["strong_identity_rate"] * 0.30
        )
        * 100
    ) if products else 0

    return {
        "version": __version__,
        "timestamp": gen_at.strftime("%b %d, %Y • %H:%M"),
        "generated_iso": gen_at.isoformat(timespec="seconds"),
        "scope": "Current stored catalog",
        "collection_label": "Latest collection",
        "products": products,
        "columnar": encode_columnar(products),
        "freshness": freshness,
        "observation_period": period,
        "price_outliers": _top_products(high_prices, n=5),
        "franchises": franchises,
        "genres": genres,
        "top_products": _top_products(products, n=10),
        "smells": smells,
        "coverage": coverage,
        "health_score": health_score,
        "price_ladder": ladder,
        "kpi": {
            "total": stats["total"],
            "avg": f"{stats['average']:.2f}" if stats["average"] is not None else "—",
            "known_prices": stats["known_prices"],
            "missing_prices": stats["missing_prices"],
            "median": f"{stats['median']:.2f}" if stats["median"] is not None else "—",
            "iqr": f"{stats['iqr']:.2f}" if stats["iqr"] is not None else "—",
            "avail_pct": availability_pct,
        },
        "kpi_min": f"{stats['minimum']:.2f}" if stats["minimum"] is not None else "—",
        "kpi_max": f"{stats['maximum']:.2f}" if stats["maximum"] is not None else "—",
        "kpi_availability_label": availability_label,
        "chart_data": chart,
        "availability": availability,
        "statistics": stats,
        "timeline": build_timeline(None, products),
        "latest_diff": None,
        "restock_analysis": None,
        "possibly_delisted": [],
        "last_run": None,
    }


def _previous_complete_prices(
    history: Sequence[Tuple[Dict[str, Any], List[Product]]],
) -> Optional[List[float]]:
    """EUR prices of the newest complete run before the latest one.

    Degraded or partial runs are skipped: comparing against a run whose prices were
    mostly unreadable would report a distribution shift that is really a parser fault.
    """
    for manifest, products in reversed(history[:-1]):
        if manifest.get("status") == "complete":
            return [
                float(p.price)
                for p in products
                if p.price is not None and p.currency == "EUR"
            ]
    return None


@dataclass(frozen=True)
class ReportSnapshot:
    """One immutable catalog or run selection, rendered into the HTML report."""

    context: Dict[str, Any]

    @classmethod
    def from_products(
        cls,
        products: Sequence[Product],
        run: Optional[Dict[str, Any]] = None,
        *,
        scope: str = "Current stored catalog",
        collection_label: str = "Latest collection",
        generated_at: Optional[datetime] = None,
        history: Optional[Sequence[Tuple[Dict[str, Any], List[Product]]]] = None,
    ) -> "ReportSnapshot":
        gen_at = as_utc(generated_at) if generated_at else datetime.now(timezone.utc)
        raw_rows = [p.model_dump() for p in products]

        prev_prices = _previous_complete_prices(history) if history else None

        context = _build_context(raw_rows, gen_at, previous_prices=prev_prices)
        context["last_run"] = run
        context["scope"] = scope
        context["collection_label"] = collection_label
        context["timeline"] = build_timeline(history, context["products"], run)

        if history and len(history) >= 2:
            old_m, old_p = history[-2]
            new_m, new_p = history[-1]
            context["latest_diff"] = compare_observations(old_m, new_m, old_p, new_p)
            context["restock_analysis"] = censored_restock_analysis(history)
            context["possibly_delisted"] = detect_possibly_delisted(history)

        return cls(context)

