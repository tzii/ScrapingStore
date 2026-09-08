# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2026-09-08

### Breaking changes

- Scrapers return `ScrapeRunResult`; library callers read `.products` and inspect `.status` rather than receiving a plain list.
- Unknown prices are nullable rather than zero; legacy database upgrades preserve a backup table and mark historical zeros `legacy_unknown`.

### Added and improved

- Compare immutable runs with `compare-runs OLD NEW`: name, availability and price changes, explicit one-sided observations, partial-run warnings and excluded weak identities.
- Show seven-day observation freshness in both themes and per-product UTC times in the modern catalog, without inferring stock from absence.
- Validate clean wheel installations on Linux and Windows with Python 3.9 and 3.13, including installed CLI commands and both bundled report templates.
- Refresh the archived showcase, improve text contrast, make terminal layout responsive, respect reduced motion, and keep theme navigation available on phones.

- Archive immutable per-run product observations with catalog updates and manifests in one transaction; retain newer catalog values when older collections finish later.
- Add `runs`, `inspect-run --products`, and `generate-report --run-id` for inspecting and replaying saved collection evidence, including empty and partial runs.
- Preserve original manifests on conflicting retries and distinguish historical records without captured observations.
- Retain collected evidence after unexpected collector errors, finalize static cancellation during delays, mark late responses incomplete, and allow recovery after rejected-only pages.
- Preserve structured complete, partial, failed, empty and cancelled collection outcomes with per-page manifests and publication gating.
- Share source-specific parsing, preserve missing prices and raw signals, and exclude unknown prices from statistics without dropping free products.
- Upsert by unique source identities and preserve weak identities without collapsing equal titles.
- Migrate legacy SQLite catalogs transactionally, retaining the original table and treating historical zero prices as unknown.
- Bound browser and static retries, handle HTTP failures explicitly, detect repeated pages, and expose a public async browser API.
- Include collection status in reports and export provenance with UTC timestamps.

- Select the browser scraper by default for the configured JavaScript source.
- Render both dashboard themes from one stored-catalog snapshot with shared statistics and report time.
- Correct even medians, include zero prices consistently, and count histogram boundary values once.
- Resolve sibling report links for local, GitHub Pages and custom output paths.
- Share search, availability and price query state between the catalog and all-pages CSV export; label summaries as full-catalog values.
- Add fixture-based CLI and browser regressions and run the browser checks in CI.

## [1.2.0] - 2026-06-12
### Added
- Redesigned analytics dashboard with filters, CSV export, availability insights, and top-product rankings.
- GitLab CI support and a `generate-report --docs` command for publishing GitHub Pages output.
- Regression tests for empty dashboards, safe data embedding, complete upserts, and CLI lifecycle behavior.

### Fixed
- Updated all mutable product fields during database upserts.
- Initialized the database for export and report-only commands.
- Escaped embedded dashboard data and dynamic HTML to prevent scraped content from injecting scripts.
- Aligned the Playwright Python package and Docker browser image versions.
- Rejected non-finite prices that would break JSON and analytics.
- Included dashboard templates in built wheels and made output paths workspace-relative.

### Changed
- Running the CLI without a command now displays help instead of starting a network scrape.
- Runtime and development dependencies are split between `requirements.txt` and `requirements-dev.txt`.
- CI now enforces the full Flake8 configuration instead of reporting style failures without failing.

## [1.1.1] - 2026-02-22
### Fixed
- Fixed availability KPI showing raw decimal instead of percentage in modern dashboard.
- Fixed Grid.js crash on null/undefined product fields (null-safe data mapping).
- Pinned Grid.js to v6.2.0 for stability.
- Added missing `rich` dependency to `pyproject.toml`.
- Added `.coverage` to `.gitignore`.

### Removed
- Removed unused `plotly` from `pyproject.toml` and `requirements.txt`.
- Removed unused `fake-useragent` from `requirements.txt`.

### Changed
- Regenerated `docs/` dashboard files from updated templates.

## [1.1.0] - 2025-12-16
### Added
- CI/CD Pipeline with GitHub Actions.
- Docker support (Dockerfile, docker-compose.yml).
- Comprehensive Type Annotations.
- Expanded Test Coverage.
- Pre-commit hooks.
- Architecture diagram in README.

## [1.0.0] - 2025-12-11
### Initial Release
- Basic scraping functionality.
- Data cleaning pipeline.
- Visualization dashboard.
