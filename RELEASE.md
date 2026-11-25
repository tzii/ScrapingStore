# ScrapingStore 3.0.0

ScrapingStore 3.0.0 moves the codebase into a proper `scrapingstore` package, replaces the 2.x dashboards with a single-file offline HTML report, adds a content-addressed raw HTML archive (`reparse`), quality gates and data forensics (`smells`), pluggable adapters (`JsonLdAdapter`, TOML `RecipeAdapter`, deterministic `MockMarket`), and a run-oriented CLI, local server, and TUI.

## Migration and compatibility

- **Package layout:** Import from `scrapingstore.*`. Legacy 2.x shims (`models.py`, `database.py`, `comparison.py`, `config.py`, `visualization/*`) remain available with `DeprecationWarning` for transition compatibility.
- **Reports:** `dashboard_terminal.html` and `generate_terminal_dashboard` are removed; legacy report calls now write the single offline HTML report, and `docs/dashboard_terminal.html` redirects to `docs/index.html`.
- **SQLite:** Back up existing databases before upgrading. Schema upgrades add typed columns (`price_minor`, `RawPageBlob`, page telemetry) while preserving run history and nullable unknown prices.
- **Runtime:** Python 3.10+, optional Playwright Chromium for JS storefronts, optional `pandas` extra (`pip install ".[pandas]"`). Core analytics and report generation require no pandas and zero network access.

## Validation

- Full test suite including real Chromium browser regressions (`pytest --run-browser`: 206 passed).
- Static checks: `ruff check scrapingstore tests scripts` and `mypy scrapingstore`.
- CI matrix verifies wheel build and isolated install with zero `site-packages` namespace pollution on Linux and Windows (Python 3.10 and 3.13).
- Visual review of the offline report across light/dark themes, filtered states, hover interactions, and `390×844` mobile viewports with zero external requests and full `prefers-reduced-motion` support.

## Rollout

1. Ensure all CI checks pass on `main`, including the clean wheel install matrix.
2. Rebuild and verify `docs/index.html` and README previews (`python -m scripts.refresh_demo && python -m scripts.capture_readme`).
3. Tag and publish `v3.0.0` on GitHub Releases with the built wheel and source archive (`python -m build`).
4. Verify the published GitHub Pages demo (`https://tzii.github.io/ScrapingStore/`).
