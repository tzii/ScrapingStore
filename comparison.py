"""Directional comparisons of immutable observations, never catalog absence claims."""

from decimal import Decimal
from typing import Any, Dict, List

from models import Product


def _price(product: Product) -> Dict[str, Any]:
    return {
        "value": product.price,
        "currency": product.currency,
        "status": product.price_status,
    }


def _changes(old: Product, new: Product) -> Dict[str, Any]:
    changes: Dict[str, Any] = {}
    for field in ("name", "availability"):
        before, after = getattr(old, field), getattr(new, field)
        if before != after:
            changes[field] = {"old": before, "new": after}
    before_price, after_price = _price(old), _price(new)
    if before_price != after_price:
        delta = None
        percent = None
        if (
            old.price is not None
            and new.price is not None
            and old.currency == new.currency
        ):
            difference = Decimal(str(new.price)) - Decimal(str(old.price))
            delta = float(difference)
            if old.price != 0:
                percent = float(difference / Decimal(str(old.price)) * 100)
        changes["price"] = {
            "old": before_price,
            "new": after_price,
            "delta": delta,
            "percent": percent,
        }
    return changes


def compare_observations(
    old_run: Dict[str, Any],
    new_run: Dict[str, Any],
    old_products: List[Product],
    new_products: List[Product],
) -> Dict[str, Any]:
    """Compare stable source keys in argument order, including partial observations.

    One-sided observations mean only that the other run did not observe that key.
    Weak and legacy identities cannot establish a match or a one-sided product.
    """
    old = {
        p.source_key: p for p in old_products if p.identity_kind in ("native", "url")
    }
    new = {
        p.source_key: p for p in new_products if p.identity_kind in ("native", "url")
    }
    matched = sorted(old.keys() & new.keys())
    changed = []
    for key in matched:
        changes = _changes(old[key], new[key])
        if changes:
            changed.append({"source_key": key, "changes": changes})
    warnings = [
        "Only observations are compared; one-sided products are not additions, "
        "removals or stock changes. Unknown prices never imply a zero price."
    ]
    if any(
        run.get("status") not in ("complete", "empty") for run in (old_run, new_run)
    ):
        warnings.append(
            "At least one run is incomplete; comparisons cover accepted observations only."
        )
    if old_run.get("scope") != new_run.get("scope"):
        warnings.append("The runs have different collection scopes.")
    return {
        "old_run": old_run,
        "new_run": new_run,
        "warnings": warnings,
        "summary": {
            "matched": len(matched),
            "changed": len(changed),
            "unchanged": len(matched) - len(changed),
            "only_in_old": len(old.keys() - new.keys()),
            "only_in_new": len(new.keys() - old.keys()),
            "excluded_old": len(old_products) - len(old),
            "excluded_new": len(new_products) - len(new),
        },
        "changes": changed,
        "only_in_old": [
            old[key].model_dump(mode="json") for key in sorted(old.keys() - new.keys())
        ],
        "only_in_new": [
            new[key].model_dump(mode="json") for key in sorted(new.keys() - old.keys())
        ],
    }
