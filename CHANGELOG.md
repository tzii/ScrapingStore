# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- **Report visual and motion polish:** Refined the single-file offline HTML report with a higher-contrast light/dark palette, hairline masthead with geometric mark, tactile active states on headline filter controls, synchronized hover crosshairs and focus dimming across overview charts, active dot highlighting in the category beeswarm, subtle reduced-motion-safe entrance/scroll animations, and refreshed GitHub Pages demo (`docs/index.html`) and README previews.

## [3.0.0] - 2026-11-23

### Major Upgrades
- **Proper `scrapingstore` package architecture:** Eliminated `site-packages` top-level namespace pollution; split cleanly into `sources/`, `transport/`, `ledger/`, `quality/`, `analytics/`, `report/`, and `cli/`.
- **Single-file offline report:** One HTML page with no external scripts, styles or fonts replaces the 2.x modern and terminal dashboards. The first sentence summarises the latest run and each number in it filters the table. Three charts follow it: how much a typical price has moved since the first run, price drops and rises per run, and stock per run. The table has one row per product and one column per run (up to 12), with price drops and rises, sold-out stretches, unreadable prices and degraded runs marked. Below it: current prices by category (dots dim to match the table's filter), a histogram of how long products stayed sold out, notes (degraded runs, products no longer seen, data checks), CSV export of the filtered rows, and light and dark themes. The catalog travels as a ~12× smaller dictionary-encoded columnar bundle.
- **Careful run-to-run changes:** Summary counts compare only the last two runs and only products with a stable ID, matching `compare-runs`. A price that changed across a run that couldn't read it is marked ▽/△ instead of being attributed to a run. The KS price-shift check compares against the last complete run, so a degraded run doesn't read as a market shift.
- **Typed SQLite Ledger & Content-Addressed Raw HTML Archive:** Added typed columns on `CollectionRun`, `ProductObservation`, `PageRecord` (with latency/bytes/fingerprint), integer minor units (`price_minor`), and gzipped `RawPageBlob` storage powering **`scrapingstore reparse`**.
- **Quality Gates & Auto Data Forensics (`smells`):** Detect silent selector drift (`degraded` status, exit code 3) and automatically flag lazy-load placeholder images, synthetic positional stock alternation, discrete `.99` pricing ladders, batch timestamps, weak identities, and KS distribution shifts.
- **Pluggable Adapters & Built-in Mock Market (`scrapingstore demo`):** Fixed Oxylabs lazy-load image extraction (`data-src`/`srcset` + placeholder rejection) and recovered 23 genres from `/assets/*.svg`; added universal Schema.org `JsonLdAdapter`, declarative TOML `RecipeAdapter`, `--type auto` smart transport fallback, route-blocking Playwright optimization, and a deterministic 5-epoch `MockMarket`.
- **Git-for-the-Shelf CLI, local server & TUI:** Added short run IDs (`@latest`, `@prev`, prefix matching), Rich live progress, `diff`, `blame`, `reparse`, `smells`, `doctor`, `demo`, `serve` (rebuilds the report on every page load), and `tui`.
- **Security, Hygiene & Tooling:** Enabled Jinja autoescape, added server CSV formula-injection escaping, atomic file writes, cwd-aware lazy config, honest default `User-Agent`, `.dockerignore` + non-root Docker user, Ruff linting, pure-Python core analytics (pandas now optional), and untracked 21 MB of orphaned v1.0 artifacts under `data/`.

### Removed
- The terminal-style report (`dashboard_terminal.html`), `generate_terminal_dashboard`, and the `terminal_dashboard_html_path` / `docs_terminal_dashboard_html_path` settings. The 2.x imports in `visualization/`, `main.py` and `config.py` still work and raise a `DeprecationWarning`; `generate_terminal_dashboard` now writes the standard report. The GitHub Pages `dashboard_terminal.html` redirects to the report.

## [2.0.1] - 2026-09-08

- Show original UTC collection dates, median EUR price, separate high-price outliers, and observation freshness.

## [2.0.0] - 2026-09-08

- Introduced `ScrapeRunResult`, nullable unknown prices, immutable per-run observation history, and `compare-runs`.

## [1.0.0] - 2025-12-11

- Initial release with Playwright/Requests scraping, cleaning, SQLite storage, and HTML dashboards.
