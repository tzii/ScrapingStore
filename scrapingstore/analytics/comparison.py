"""Directional comparisons of immutable observations using exact integer minor units."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from scrapingstore.ledger.models import Product


def _price(product: Product) -> Dict[str, Any]:
    return {
        "value": product.price,
        "minor": product.price_minor,
        "currency": product.currency,
        "status": product.price_status,
    }


def _changes(old: Product, new: Product) -> Dict[str, Any]:
    changes: Dict[str, Any] = {}
    for field in ("name", "availability", "category"):
        before, after = getattr(old, field), getattr(new, field)
        if before != after:
            changes[field] = {"old": before, "new": after}
    before_price, after_price = _price(old), _price(new)
    if (
        before_price["value"] != after_price["value"]
        or before_price["currency"] != after_price["currency"]
        or before_price["status"] != after_price["status"]
    ):
        delta = None
        delta_minor = None
        percent = None
        if (
            old.price is not None
            and new.price is not None
            and old.currency == new.currency
        ):
            difference = Decimal(str(new.price)) - Decimal(str(old.price))
            delta = float(difference)
            if old.price_minor is not None and new.price_minor is not None:
                delta_minor = new.price_minor - old.price_minor
            if old.price != 0:
                percent = round(float(difference / Decimal(str(old.price)) * 100), 2)
        changes["price"] = {
            "old": {k: before_price[k] for k in ("value", "currency", "status")},
            "new": {k: after_price[k] for k in ("value", "currency", "status")},
            "delta": delta,
            "delta_minor": delta_minor,
            "percent": percent,
        }
    return changes


def compare_observations(
    old_run: Dict[str, Any],
    new_run: Dict[str, Any],
    old_products: List[Product],
    new_products: List[Product],
) -> Dict[str, Any]:
    """Compare stable source keys in argument order, preserving epistemic honesty."""
    old = {
        p.source_key: p for p in old_products if p.identity_kind in ("native", "url")
    }
    new = {
        p.source_key: p for p in new_products if p.identity_kind in ("native", "url")
    }
    matched = sorted(old.keys() & new.keys())
    changed = []
    price_drops = 0
    price_rises = 0
    restocks = 0
    stockouts = 0

    for key in matched:
        changes = _changes(old[key], new[key])
        if changes:
            item_name = new[key].name
            changed.append(
                {"source_key": key, "name": item_name, "changes": changes}
            )
            if "price" in changes and changes["price"]["delta"] is not None:
                if changes["price"]["delta"] < 0:
                    price_drops += 1
                elif changes["price"]["delta"] > 0:
                    price_rises += 1
            if "availability" in changes:
                a_old = changes["availability"]["old"]
                a_new = changes["availability"]["new"]
                if a_old == "Out of Stock" and a_new == "In Stock":
                    restocks += 1
                elif a_old == "In Stock" and a_new == "Out of Stock":
                    stockouts += 1

    warnings = [
        "Only observations are compared; one-sided products are not additions, "
        "removals or stock changes. Unknown prices never imply a zero price."
    ]
    if any(
        run.get("status") not in ("complete", "empty") for run in (old_run, new_run)
    ):
        warnings.append(
            "At least one run is incomplete or degraded; comparisons cover accepted observations only."
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
            "price_drops": price_drops,
            "price_rises": price_rises,
            "restocks": restocks,
            "stockouts": stockouts,
        },
        "changes": changed,
        "only_in_old": [
            old[key].model_dump(mode="json") for key in sorted(old.keys() - new.keys())
        ],
        "only_in_new": [
            new[key].model_dump(mode="json") for key in sorted(new.keys() - old.keys())
        ],
    }


def format_diff_summary(diff: Dict[str, Any], *, max_rows: int = 15) -> str:
    """Render a compact, readable summary of a comparison payload."""
    s = diff["summary"]
    old_id = (diff["old_run"].get("short_id") or diff["old_run"].get("run_id") or "old")[:8]
    new_id = (diff["new_run"].get("short_id") or diff["new_run"].get("run_id") or "new")[:8]
    lines = [
        f"Diff {old_id} -> {new_id}: {s['matched']} matched, {s['changed']} changed, "
        f"{s['only_in_new']} only in new, {s['only_in_old']} only in old",
        f"Moves: {s['price_drops']} price drops, {s['price_rises']} rises, "
        f"{s['restocks']} restocks, {s['stockouts']} stockouts",
    ]
    for entry in diff["changes"][:max_rows]:
        parts = []
        ch = entry["changes"]
        if "price" in ch:
            p = ch["price"]
            old_v = "—" if p["old"]["value"] is None else f"€{p['old']['value']:.2f}"
            new_v = "—" if p["new"]["value"] is None else f"€{p['new']['value']:.2f}"
            pct = f" ({p['percent']:+.1f}%)" if p.get("percent") is not None else ""
            parts.append(f"price {old_v} -> {new_v}{pct}")
        if "availability" in ch:
            a = ch["availability"]
            parts.append(f"stock {a['old']} -> {a['new']}")
        if "name" in ch:
            parts.append(f"renamed from {ch['name']['old']!r}")
        lines.append(f"  - {entry.get('name') or entry['source_key']}: " + "; ".join(parts))
    if len(diff["changes"]) > max_rows:
        lines.append(f"  ... and {len(diff['changes']) - max_rows} more changes")
    return "\n".join(lines)
