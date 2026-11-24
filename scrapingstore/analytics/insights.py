"""Pure-Python analytics: exact quantiles, price ladders, TF-IDF franchises, censored restocks."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scrapingstore.io_utils import as_utc
from scrapingstore.ledger.models import Product

_STOP_WORDS = {
    "the", "of", "and", "a", "in", "for", "to", "is", "on", "at", "by", "an",
    "it", "with", "from", "edition", "game", "video", "new", "pro", "set", "kit",
    "deluxe", "cut", "vol", "part", "chapter", "episode", "series", "collection",
    "remastered", "anniversary", "ultimate", "complete", "goty", "standard",
    "special", "pack", "bundle", "directors", "collectors", "world", "war",
    "age", "heroes", "legend", "chronicles", "origins", "rebirth", "zero",
}

_ROMAN_NUMERALS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile matching numpy/pandas default."""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("Cannot compute quantile of empty sequence")
    if n == 1:
        return float(sorted_vals[0])
    pos = q * (n - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]))


def _extract_eur_prices(products: Sequence[Dict[str, Any]]) -> List[float]:
    return [
        float(p["price"])
        for p in products
        if p.get("price") is not None
        and math.isfinite(float(p["price"]))
        and float(p["price"]) >= 0
        and (p.get("currency") or "EUR") == "EUR"
    ]


def price_statistics(products: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute exact summary statistics without requiring pandas."""
    total = len(products)
    prices = sorted(_extract_eur_prices(products))
    known = len(prices)
    missing = sum(1 for p in products if p.get("price") is None)
    if not prices:
        return {
            "total": total,
            "average": None,
            "minimum": None,
            "maximum": None,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "std_dev": None,
            "known_prices": 0,
            "missing_prices": missing,
            "distinct_prices": 0,
        }
    avg = sum(prices) / known
    median = _quantile(prices, 0.5)
    q1 = _quantile(prices, 0.25)
    q3 = _quantile(prices, 0.75)
    variance = sum((x - avg) ** 2 for x in prices) / known
    return {
        "total": total,
        "average": avg,
        "minimum": prices[0],
        "maximum": prices[-1],
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "std_dev": math.sqrt(variance),
        "known_prices": known,
        "missing_prices": missing,
        "distinct_prices": len(set(prices)),
    }


def price_histogram(products: Sequence[Dict[str, Any]], *, bin_count: int = 8) -> Dict[str, Any]:
    """Equal-width half-open bands [start, end) with Tukey IQR outlier separation."""
    prices = sorted(_extract_eur_prices(products))
    threshold: Optional[float] = None
    outliers: List[float] = []
    if len(prices) >= 8:
        q1 = _quantile(prices, 0.25)
        q3 = _quantile(prices, 0.75)
        threshold = float(q3 + 1.5 * (q3 - q1))
        main_prices = [p for p in prices if p <= threshold]
        outliers = [p for p in prices if p > threshold]
    else:
        main_prices = list(prices)

    result: Dict[str, Any] = {
        "labels": ["No Data"],
        "interval_labels": ["No Data"],
        "bounds": [],
        "counts": [0],
        "main_count": len(main_prices),
        "outlier_count": len(outliers),
        "outlier_threshold": threshold,
        "total": len(prices),
    }
    if not prices or not main_prices:
        return result

    min_price = math.floor(main_prices[0])
    max_price = float(main_prices[-1])
    step = max(5, math.ceil((max_price - min_price) / bin_count))

    labels: List[str] = []
    interval_labels: List[str] = []
    bounds: List[List[float]] = []
    counts: List[int] = []
    for index in range(bin_count):
        start = min_price + index * step
        end = start + step
        is_last = index == bin_count - 1
        count = sum(
            1
            for p in main_prices
            if (start <= p <= end if is_last else start <= p < end)
        )
        labels.append(f"{start}-{end}")
        interval_labels.append(f"[{start},{end}]" if is_last else f"[{start},{end})")
        bounds.append([float(start), float(end)])
        counts.append(count)

    result.update(
        labels=labels,
        interval_labels=interval_labels,
        bounds=bounds,
        counts=counts,
    )
    return result


def price_ladder(products: Sequence[Dict[str, Any]], *, max_tiers: int = 120) -> Dict[str, Any]:
    """Expose discrete pricing structure (e.g., 72 exact .99 price points)."""
    prices = _extract_eur_prices(products)
    if not prices:
        return {"tiers": [], "distinct_count": 0, "dominant_ending": None, "dominant_ending_pct": 0.0}
    counts = Counter(round(p, 2) for p in prices)
    endings = Counter(round((p - int(p)) * 100) for p in prices)
    dom_cent, dom_count = endings.most_common(1)[0]
    tiers = [
        {"price": price, "count": count}
        for price, count in sorted(counts.items())[:max_tiers]
    ]
    return {
        "tiers": tiers,
        "distinct_count": len(counts),
        "dominant_ending": f".{dom_cent:02d}",
        "dominant_ending_pct": round(dom_count / len(prices), 4),
    }


def _tokenize_title(name: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9']+", name)
    cleaned: List[str] = []
    for tok in tokens:
        low = tok.lower().strip("'")
        if len(low) < 2 or low in _ROMAN_NUMERALS or low.isdigit():
            continue
        cleaned.append(low)
    return cleaned


def detect_franchises_tfidf(
    products: Sequence[Dict[str, Any]], *, top_n: int = 10
) -> List[Dict[str, Any]]:
    """Extract meaningful franchise phrases (bigrams + salient unigrams) without stopword noise."""
    if not products:
        return []

    bigram_docs: Counter[str] = Counter()
    unigram_docs: Counter[str] = Counter()
    display_map: Dict[str, Counter[str]] = defaultdict(Counter)

    for row in products:
        name = str(row.get("name") or "")
        raw_tokens = re.findall(r"[A-Za-z0-9']+", name)
        norm = []
        for raw in raw_tokens:
            low = raw.lower().strip("'")
            if len(low) < 2 or low in _ROMAN_NUMERALS or low.isdigit():
                continue
            norm.append((low, raw.strip("'")))

        seen_bi: set[str] = set()
        seen_uni: set[str] = set()

        for i in range(len(norm) - 1):
            w1, r1 = norm[i]
            w2, r2 = norm[i + 1]
            if w1 in _STOP_WORDS and w2 in _STOP_WORDS:
                continue
            if w1 in ("the", "of", "and", "in", "for", "to", "a", "an"):
                continue
            if w2 in ("the", "of", "and", "in", "for", "to", "a", "an"):
                continue
            key = f"{w1} {w2}"
            if key not in seen_bi:
                bigram_docs[key] += 1
                display_map[key][f"{r1} {r2}"] += 1
                seen_bi.add(key)

        for w, r in norm:
            if len(w) >= 4 and w not in _STOP_WORDS and w not in seen_uni:
                unigram_docs[w] += 1
                display_map[w][r] += 1
                seen_uni.add(w)

    # Prefer multi-word franchises when they appear >= 2 times, suppressing subsumed unigrams
    selected: List[Tuple[str, str, int, float]] = []
    covered_words: set[str] = set()
    n_docs = max(len(products), 1)

    for key, count in bigram_docs.most_common(top_n * 3):
        if count < 2:
            continue
        # Score favors frequent, coherent bigrams (IDF-damped so generic combos lose)
        score = count * (1.25 + math.log(1.0 + n_docs / (count + 1)))
        label = display_map[key].most_common(1)[0][0]
        selected.append((key, label, count, score))
        covered_words.update(key.split())
        if len(selected) >= top_n:
            break

    for key, count in unigram_docs.most_common(top_n * 3):
        if count < 2 or key in covered_words:
            continue
        score = count * math.log(1.0 + n_docs / (count + 1))
        label = display_map[key].most_common(1)[0][0]
        selected.append((key, label, count, score))

    selected.sort(key=lambda item: (-item[2], -item[3], item[1]))
    seen_labels: set[str] = set()
    output: List[Dict[str, Any]] = []
    for _, label, count, _ in selected:
        canon = label.casefold()
        if canon in seen_labels:
            continue
        seen_labels.add(canon)
        output.append({"name": label, "count": count})
        if len(output) >= top_n:
            break
    return output


def genre_breakdown(products: Sequence[Dict[str, Any]], *, top_n: int = 12) -> List[Dict[str, Any]]:
    """Aggregate products by extracted category/genre with median price per genre."""
    buckets: Dict[str, List[float]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for p in products:
        cat = p.get("category") or "Uncategorized"
        counts[cat] += 1
        if p.get("price") is not None and (p.get("currency") or "EUR") == "EUR":
            buckets[cat].append(float(p["price"]))
    return [
        {
            "name": cat,
            "count": count,
            "median_price": round(_quantile(sorted(buckets[cat]), 0.5), 2)
            if buckets[cat]
            else None,
        }
        for cat, count in counts.most_common(top_n)
    ]


def availability_stats(products: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, int], str, str]:
    """Count last-observed availability signals without claiming live inventory health."""
    total = len(products)
    in_stock = 0
    out_of_stock = 0
    for p in products:
        status = str(p.get("availability") or "Unknown").strip().casefold()
        if status == "in stock":
            in_stock += 1
        elif status == "out of stock":
            out_of_stock += 1
    unknown = max(total - in_stock - out_of_stock, 0)
    if total == 0:
        return {"in_stock": 0, "out_of_stock": 0, "unknown": 0}, "0%", "No Data"
    pct = int((in_stock / total) * 100)
    return (
        {"in_stock": in_stock, "out_of_stock": out_of_stock, "unknown": unknown},
        f"{pct}%",
        "Last observed in stock",
    )


def observation_period(products: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute UTC observation date span without substituting report generation time."""
    parsed_dates: List[datetime] = []
    for p in products:
        raw = p.get("scraped_at")
        if not raw:
            continue
        try:
            if isinstance(raw, datetime):
                parsed_dates.append(as_utc(raw))
            else:
                text = str(raw).strip()
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                parsed_dates.append(as_utc(datetime.fromisoformat(text)))
        except ValueError:
            continue
    if not parsed_dates:
        return {
            "label": (
                "Collection dates unavailable" if products else "No observations yet"
            ),
            "start": None,
            "end": None,
            "missing": len(products),
        }
    first, last = min(parsed_dates), max(parsed_dates)
    label = first.strftime("%d %B %Y")
    if first.date() != last.date():
        label += " – " + last.strftime("%d %B %Y")
    return {
        "label": "Data collected " + label,
        "start": first.isoformat(),
        "end": last.isoformat(),
        "missing": len(products) - len(parsed_dates),
    }


def censored_restock_analysis(
    history: Sequence[Tuple[Dict[str, Any], List[Product]]]
) -> Dict[str, Any]:
    """Kaplan–Meier-aware stockout duration & restock cadence analysis.

    Crucially, runs where a SKU was NOT observed are treated as right-censored
    intervals — never fabricated as Out of Stock or In Stock transitions.
    """
    if len(history) < 2:
        return {
            "runs_analyzed": len(history),
            "completed_restocks": 0,
            "right_censored_stockouts": 0,
            "median_stockout_days": None,
            "avg_stockout_days": None,
            "restock_rate_pct": None,
        }

    # Chronological runs (oldest -> newest)
    run_times: List[datetime] = []
    run_maps: List[Dict[str, Product]] = []
    for manifest, prods in history:
        raw_ts = str(manifest.get("started_at", ""))
        if raw_ts.endswith("Z"):
            raw_ts = raw_ts[:-1] + "+00:00"
        run_times.append(as_utc(datetime.fromisoformat(raw_ts)))
        run_maps.append(
            {p.source_key: p for p in prods if p.identity_kind in ("native", "url")}
        )

    all_keys = sorted({k for m in run_maps for k in m})
    completed_durations: List[float] = []
    censored_durations: List[float] = []

    for key in all_keys:
        out_start: Optional[datetime] = None
        last_seen_out: Optional[datetime] = None
        for idx, m in enumerate(run_maps):
            prod = m.get(key)
            if prod is None:
                # Unseen = censored, do not change state
                continue
            avail = prod.availability.strip().casefold()
            ts = run_times[idx]
            if avail == "out of stock":
                if out_start is None:
                    out_start = ts
                last_seen_out = ts
            elif avail == "in stock" and out_start is not None:
                days = max(0.0, (ts - out_start).total_seconds() / 86400.0)
                completed_durations.append(round(days, 2))
                out_start = None
                last_seen_out = None
        if out_start is not None and last_seen_out is not None:
            days = max(0.0, (last_seen_out - out_start).total_seconds() / 86400.0)
            censored_durations.append(round(days, 2))

    total_episodes = len(completed_durations) + len(censored_durations)
    sorted_done = sorted(completed_durations)
    return {
        "runs_analyzed": len(history),
        "completed_restocks": len(completed_durations),
        "right_censored_stockouts": len(censored_durations),
        "median_stockout_days": round(_quantile(sorted_done, 0.5), 2)
        if sorted_done
        else None,
        "avg_stockout_days": round(sum(sorted_done) / len(sorted_done), 2)
        if sorted_done
        else None,
        "restock_rate_pct": round((len(completed_durations) / total_episodes) * 100, 1)
        if total_episodes
        else None,
        # Per-episode days, for the report's chart: completed episodes ended with a
        # restock; censored ones were still sold out when last seen ("at least" this long).
        "completed_durations": sorted_done,
        "censored_durations": sorted(censored_durations),
    }


def detect_possibly_delisted(
    history: Sequence[Tuple[Dict[str, Any], List[Product]]],
    *,
    min_consecutive_misses: int = 2,
) -> List[Dict[str, Any]]:
    """Flag possibly delisted SKUs ONLY after K consecutive complete, full-scope runs miss them."""
    full_complete = [
        (m, prods)
        for m, prods in history
        if m.get("status") == "complete"
        and m.get("scope", {}).get("requested_pages") is None
    ]
    if len(full_complete) < min_consecutive_misses + 1:
        return []

    seen_sets = [
        {p.source_key: p for p in prods if p.identity_kind in ("native", "url")}
        for _, prods in full_complete
    ]
    tail = seen_sets[-min_consecutive_misses:]
    earlier = seen_sets[:-min_consecutive_misses]

    candidates: List[Dict[str, Any]] = []
    ever_seen: Dict[str, Tuple[int, Product]] = {}
    for run_idx, mapping in enumerate(earlier):
        for key, prod in mapping.items():
            ever_seen[key] = (run_idx, prod)

    for key, (last_idx, prod) in ever_seen.items():
        if all(key not in t for t in tail):
            consecutive_misses = len(seen_sets) - 1 - last_idx
            confidence = (
                "high" if consecutive_misses >= 3 else "medium"
            )
            candidates.append(
                {
                    "source_key": key,
                    "name": prod.name,
                    "last_price": prod.price,
                    "currency": prod.currency,
                    "last_seen_run": full_complete[last_idx][0].get("run_id"),
                    "consecutive_full_misses": consecutive_misses,
                    "confidence": confidence,
                }
            )
    candidates.sort(key=lambda c: (-c["consecutive_full_misses"], c["name"]))
    return candidates
