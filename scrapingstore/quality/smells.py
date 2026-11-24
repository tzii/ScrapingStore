"""Self-skeptical Data Forensics engine that questions its own scraped data."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from scrapingstore.ledger.models import Product


@dataclass(frozen=True)
class DataSmell:
    code: str
    severity: str  # "error" | "warn" | "info"
    title: str
    metric: str
    detail: str
    remediation: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def ks_statistic(sample_a: Sequence[float], sample_b: Sequence[float]) -> float:
    """Two-sample Kolmogorov-Smirnov statistic (pure Python, 0.0 to 1.0)."""
    if not sample_a or not sample_b:
        return 0.0
    a = sorted(sample_a)
    b = sorted(sample_b)
    n_a, n_b = len(a), len(b)
    i = j = 0
    max_diff = 0.0
    while i < n_a and j < n_b:
        if a[i] < b[j]:
            i += 1
        elif b[j] < a[i]:
            j += 1
        else:
            val = a[i]
            while i < n_a and a[i] == val:
                i += 1
            while j < n_b and b[j] == val:
                j += 1
        diff = abs(i / n_a - j / n_b)
        if diff > max_diff:
            max_diff = diff
    return round(max_diff, 4)


def detect_smells(
    products: Sequence[Product | Dict[str, Any]],
    *,
    previous_prices: Optional[Sequence[float]] = None,
) -> List[DataSmell]:
    """Audit a product snapshot for synthetic patterns, extraction bugs, and structural quirks."""
    if not products:
        return []

    rows: List[Dict[str, Any]] = [
        p.model_dump() if isinstance(p, Product) else dict(p) for p in products
    ]
    n = len(rows)
    smells: List[DataSmell] = []

    # 1. Lazy-load placeholder images
    placeholder_count = sum(
        1
        for r in rows
        if isinstance(r.get("image_url"), str)
        and (
            r["image_url"].strip().lower().startswith("data:")
            or "placeholder" in r["image_url"].strip().lower()
        )
    )
    if placeholder_count > 0:
        pct = placeholder_count / n
        smells.append(
            DataSmell(
                code="lazy_placeholder_images",
                severity="error" if pct >= 0.2 else "warn",
                title="Lazy-load image placeholders",
                metric=f"{pct:.1%}",
                detail=(
                    f"{placeholder_count:,} of {n:,} rows captured placeholder "
                    "data: URLs instead of real product artwork."
                ),
                remediation="Inspect data-src/srcset in the adapter and run `scrapingstore reparse`.",
            )
        )

    # 2. Synthetic positional stock alternation (e.g. Oxylabs even=In Stock, odd=Out of Stock)
    if n >= 20:
        avail_seq = [str(r.get("availability") or "Unknown").strip().casefold() for r in rows]
        in_out_only = [s for s in avail_seq if s in ("in stock", "out of stock")]
        if len(in_out_only) >= 20:
            transitions = sum(
                1 for idx in range(1, len(in_out_only)) if in_out_only[idx] != in_out_only[idx - 1]
            )
            alt_ratio = transitions / (len(in_out_only) - 1)
            if alt_ratio >= 0.92:
                smells.append(
                    DataSmell(
                        code="synthetic_stock_alternation",
                        severity="warn",
                        title="Synthetic positional stock alternation",
                        metric=f"alt={alt_ratio:.0%}",
                        detail=(
                            f"Availability flips between In Stock and Out of Stock on "
                            f"{alt_ratio:.1%} of consecutive rows — strongly indicating a "
                            "sandbox modulo pattern rather than live inventory."
                        ),
                        remediation="Treat stock KPI as a source artifact; verify against real storefront signals.",
                    )
                )

    # 3. Missing / unparseable prices
    missing_prices = sum(1 for r in rows if r.get("price") is None)
    if missing_prices > 0:
        miss_pct = missing_prices / n
        if miss_pct >= 0.15:
            smells.append(
                DataSmell(
                    code="high_missing_prices",
                    severity="error" if miss_pct >= 0.35 else "warn",
                    title="Elevated missing price rate",
                    metric=f"{miss_pct:.1%}",
                    detail=(
                        f"{missing_prices:,} of {n:,} items have null prices. "
                        "Excluded from averages/histograms; never coerced to zero."
                    ),
                    remediation="Run `scrapingstore doctor --probe` to check whether the price selector still matches.",
                )
            )

    # 4. Discrete pricing ladder / uniform cents ending (e.g., 100% .99)
    eur_prices = [
        float(r["price"])
        for r in rows
        if r.get("price") is not None and (r.get("currency") or "EUR") == "EUR"
    ]
    if len(eur_prices) >= 20:
        distinct = len(set(eur_prices))
        cents = Counter(round((p - int(p)) * 100) for p in eur_prices)
        top_cent, top_cent_count = cents.most_common(1)[0]
        cent_ratio = top_cent_count / len(eur_prices)
        if cent_ratio >= 0.90 or (distinct <= max(20, len(eur_prices) // 25)):
            smells.append(
                DataSmell(
                    code="discrete_pricing_ladder",
                    severity="info",
                    title=f"Discrete .{top_cent:02d} pricing ladder",
                    metric=f"{distinct} tiers",
                    detail=(
                        f"{cent_ratio:.0%} of {len(eur_prices):,} EUR prices end in "
                        f".{top_cent:02d} across only {distinct} distinct price points."
                    ),
                    remediation="No action needed; the store prices in fixed steps.",
                )
            )

    # 5. Constant / identical observation timestamps
    timestamps = [str(r.get("scraped_at") or "")[:19] for r in rows if r.get("scraped_at")]
    if len(timestamps) >= 10:
        top_ts, ts_count = Counter(timestamps).most_common(1)[0]
        if ts_count / len(timestamps) >= 0.95:
            smells.append(
                DataSmell(
                    code="constant_timestamps",
                    severity="info",
                    title="Uniform batch timestamp",
                    metric=f"{ts_count / len(timestamps):.0%}",
                    detail=(
                        f"All {ts_count:,} observations share {top_ts}Z. "
                        "Normal when one collection saved every row."
                    ),
                    remediation="No action needed — normal for single-batch or archived snapshots.",
                )
            )

    # 6. Legacy or weak identity dominance
    weak_or_legacy = sum(
        1 for r in rows if r.get("identity_kind") not in ("native", "url")
    )
    if weak_or_legacy > 0 and weak_or_legacy / n >= 0.5:
        smells.append(
            DataSmell(
                code="weak_identity_dominance",
                severity="warn",
                title="Legacy/weak identities limit diffing",
                metric=f"{weak_or_legacy / n:.0%}",
                detail=(
                    f"{weak_or_legacy:,} of {n:,} items lack a native ID or stable product URL, "
                    "so run-to-run diffs cannot reliably match them."
                ),
                remediation="Collect with a v2+ adapter or run `scrapingstore demo` for native-ID multi-run history.",
            )
        )

    # 7. Distribution shift vs previous run (KS test)
    if previous_prices and eur_prices and len(previous_prices) >= 10 and len(eur_prices) >= 10:
        ks = ks_statistic(previous_prices, eur_prices)
        if ks >= 0.20:
            smells.append(
                DataSmell(
                    code="price_distribution_shift",
                    severity="warn",
                    title="Price distribution shift detected",
                    metric=f"KS={ks:.2f}",
                    detail=(
                        "Significant shift in price distribution compared to the previous run. "
                        "Verify whether this is a real market promotion or parser drift."
                    ),
                    remediation="Run `scrapingstore diff @prev @latest` to inspect top price movers.",
                )
            )

    return smells
