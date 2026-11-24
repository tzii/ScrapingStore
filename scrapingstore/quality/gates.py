"""Per-run field-coverage quality gates that turn silent parser drift into `degraded`."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from scrapingstore.ledger.models import Product


def field_coverage(products: Sequence[Product]) -> Dict[str, float]:
    """Compute fill-rate ratios (0.0–1.0) across key extracted fields."""
    total = len(products)
    if total == 0:
        return {
            "count": 0.0,
            "known_price_rate": 0.0,
            "known_availability_rate": 0.0,
            "real_image_rate": 0.0,
            "strong_identity_rate": 0.0,
            "category_rate": 0.0,
        }
    known_price = sum(1 for p in products if p.price is not None)
    known_avail = sum(
        1 for p in products if (p.availability or "").strip().casefold() != "unknown"
    )
    real_img = sum(
        1
        for p in products
        if p.image_url and not p.image_url.strip().lower().startswith("data:")
    )
    strong_id = sum(1 for p in products if p.identity_kind in ("native", "url"))
    has_cat = sum(1 for p in products if p.category)
    return {
        "count": float(total),
        "known_price_rate": round(known_price / total, 4),
        "known_availability_rate": round(known_avail / total, 4),
        "real_image_rate": round(real_img / total, 4),
        "strong_identity_rate": round(strong_id / total, 4),
        "category_rate": round(has_cat / total, 4),
    }


def evaluate_quality_gate(
    products: Sequence[Product],
    prior_runs: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    min_price_rate_drop: float = 0.25,
    min_identity_rate_drop: float = 0.25,
    absolute_price_collapse: float = 0.20,
) -> Dict[str, Any]:
    """Compare a run's field coverage against rolling baselines to detect silent drift."""
    metrics = field_coverage(products)
    reasons: List[str] = []

    baselines: List[Dict[str, float]] = []
    for run in prior_runs or ():
        if run.get("status") != "complete":
            continue
        qg = run.get("quality_gate")
        if isinstance(qg, dict) and isinstance(qg.get("metrics"), dict):
            if qg["metrics"].get("count", 0) > 0:
                baselines.append(qg["metrics"])

    baseline_summary: Optional[Dict[str, float]] = None
    if baselines and len(products) >= 5:
        recent = baselines[:5]
        baseline_summary = {
            key: round(sum(b.get(key, 0.0) for b in recent) / len(recent), 4)
            for key in (
                "known_price_rate",
                "known_availability_rate",
                "real_image_rate",
                "strong_identity_rate",
            )
        }
        price_drop = (
            baseline_summary["known_price_rate"] - metrics["known_price_rate"]
        )
        if price_drop >= min_price_rate_drop:
            reasons.append(
                f"price_selector_drift: known price rate dropped from "
                f"{baseline_summary['known_price_rate']:.0%} to "
                f"{metrics['known_price_rate']:.0%}"
            )
        id_drop = (
            baseline_summary["strong_identity_rate"] - metrics["strong_identity_rate"]
        )
        if id_drop >= min_identity_rate_drop:
            reasons.append(
                f"identity_contract_drift: strong identity rate dropped from "
                f"{baseline_summary['strong_identity_rate']:.0%} to "
                f"{metrics['strong_identity_rate']:.0%}"
            )
        avail_drop = (
            baseline_summary["known_availability_rate"]
            - metrics["known_availability_rate"]
        )
        if avail_drop >= 0.35:
            reasons.append(
                f"availability_selector_drift: known availability dropped from "
                f"{baseline_summary['known_availability_rate']:.0%} to "
                f"{metrics['known_availability_rate']:.0%}"
            )
    elif len(products) >= 10 and metrics["known_price_rate"] < absolute_price_collapse:
        reasons.append(
            f"price_extraction_collapse: only {metrics['known_price_rate']:.0%} "
            f"of {len(products)} products have a usable price"
        )

    return {
        "passed": len(reasons) == 0,
        "status": "ok" if not reasons else "degraded",
        "metrics": metrics,
        "baseline": baseline_summary,
        "reasons": reasons,
    }
