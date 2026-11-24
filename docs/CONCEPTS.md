# Epistemic Evidence Model & Architecture

ScrapingStore keeps a record of what each run actually saw, rather than a single overwritten catalog. Every value shown in the CLI, the CSV export or the HTML report carries its provenance and how certain it is.

---

## 1. Core Epistemic Contracts

1. **Unknown is never zero.** Missing, ambiguous, negative, or unsupported prices are stored as `price = None` (`price_minor = None`) alongside `price_raw` and `price_status`. Free items (`0.00 €`) remain explicitly `0` with `price_status = "known"`.
2. **Absence is right-censored, never "out of stock" or "removed".** If a product is not seen in a run, ScrapingStore does not overwrite its last-known stock signal and never fabricates a deletion. `compare-runs` / `diff` reports `only_in_old` and `only_in_new` neutrally.
3. **Confidence-graded delisting.** A product is flagged as *possibly delisted* only after `K ≥ 2` consecutive **complete, full-scope** runs fail to observe it (`medium` at 2 misses, `high` at 3+).
4. **Censored restock analysis.** Stockout durations count transitions `Out of Stock -> In Stock` across chronological runs; runs where a SKU was unobserved are treated as right-censored intervals rather than transitions.
5. **Observation age ≠ stock state.** Freshness is evaluated separately and never changes the last observed availability. The report adds a note when its latest run is more than 7 days older than the report itself.

---

## 2. How the report shows evidence

The report has one row per product and one column per run (the last 12 by default).

| What was observed | In the report | Meaning |
|---|---|---|
| Same price as the last readable one | Thin line between values | Unchanged |
| Price changed since the previous run | ▼ or ▲ before the new price | Dropped or rose between two consecutive runs; counted in the summary |
| Price changed, but the run before couldn't read it or didn't see the product | ▽ or △ before the new price | It changed, but which run it changed in is unknown; not counted in the summary |
| Price unreadable | `?` | Product seen, price unknown (never zero) |
| Out of stock | Grey band across the runs | Sold out while the band lasts |
| Not seen | Empty cell, "last seen" next to the name | Not observed; never treated as sold out or removed |
| Degraded run | ⚠ and "% read" under the run date | Too few prices read; explained in the notes |
| No stable product ID | No change markers | Can't be matched across runs |

The charts use the same rules:

- **Typical price change** chains the geometric mean of same-product price ratios from each run to the previous run that had comparable prices. Only products with a stable ID and a single currency count. A degraded run is drawn as a hollow point.
- **Price changes per run** draws drops below the line and rises above it. Changes whose run is unknown (▽/△) are hollow segments stacked on the end, so the solid part matches the summary counts.
- **Stock per run** counts in stock, sold out and unknown among the products seen in each run. Products not seen are left out rather than counted as sold out.
- **Prices by category** shows the latest run's euro prices. Prices far above the rest (beyond 1.5 × the interquartile range) are listed under the chart instead of stretching its scale.
- **How long products stayed sold out** puts each sold-out stretch in a bin by its length in runs. A stretch that ended in a restock is filled; one still sold out at the last observation is hollow, because its length is only a lower bound.

---

## 3. Quality Gates & Auto Data Forensics

Every collection passes through `scrapingstore/quality/gates.py` before publication:

- Computes per-run fill rates (`known_price_rate`, `known_availability_rate`, `real_image_rate`, `strong_identity_rate`, `category_rate`).
- Compares against the rolling baseline of the last 5 `complete` runs.
- If a selector silently breaks (e.g., known price rate drops ≥25 percentage points or identity contract collapses), the run is marked **`degraded`** (exit code `3`) and automatic report/CSV publication is blocked unless `--allow-partial` is passed.

Separately, `scrapingstore/quality/smells.py` audits any snapshot for structural quirks:
- **Lazy-load placeholder images** (`data:image/gif` or `placeholder` URLs)
- **Synthetic positional stock alternation** (e.g., `pos % 2` alternating stock)
- **Discrete pricing ladders** (e.g., 100% `.99` across 72 discrete tiers)
- **Uniform batch timestamps**
- **Legacy/weak identity dominance**
- **Two-sample KS distribution shift** between the latest run and the last complete run before it (degraded runs are skipped, so a parser fault doesn't read as a market shift)

---

## 4. Content-Addressed Archive & Time-Travel Reparsing

When `archive_html` is enabled (the default), every fetched page's raw bytes are SHA-256 hashed, gzipped, and deduplicated in the `rawpageblob` SQLite table linked from `pagerecord`.

Running `scrapingstore reparse <run>` replays those archived HTML bytes through `ArchiveTransport` using the current parser version and prints a **Parser Diff** (recovered images, categories, prices) before optionally committing with `--apply`. This makes parser bugs recoverable retroactively and separates parser drift from real market changes.
