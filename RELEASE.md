# ScrapingStore 2.0.0

This release makes the portfolio's product evidence inspectable: immutable collection history, saved-run reports, directional comparisons, and observation freshness in both dashboard themes. It also hardens collection outcomes, unknown prices, identity handling and installation checks.

## Migration and compatibility

- **Library API:** `scrape()` now returns `ScrapeRunResult`. Read `.products`, `.status` and `.manifest()`. Async callers use `await scrape_async()`.
- **SQLite:** stop collection writers and back up the entire database before first launch. Startup migrates legacy catalog rows transactionally, retaining `product_legacy_v1`, and adds observation history. Historical zero prices become unknown (`null` with `legacy_unknown`). An existing backup table is never overwritten.
- **History:** old manifest-only runs remain inspectable but cannot be replayed or compared. No historical observations are fabricated. Legacy identities require deliberate reconciliation; names are not join keys.
- **Runtime:** Python 3.9+, Playwright 1.60.0 and Chromium for browser collection. No new production dependencies for comparisons or freshness. Build isolation requires setuptools 77+ for the declared license metadata.

## Risk and validation

**Severity: medium after mitigation.** The main risk is migration and downstream code that assumes a list return or treats unknown prices as zero. Backups and the explicit API migration address this; downgrading against the migrated database is not the rollback path.

Validation includes transactional history and migration tests, partial collection and unknown-price regressions, comparison tests, actual Chromium report interactions, and clean installed-wheel commands outside the source checkout. The CI matrix checks wheel installation on Linux/Windows with Python 3.9/3.13. Visual review covers both themes at desktop and 390px phone widths.

The showcase retains December 2025 observations and says so. External dashboard CDN assets remain a runtime dependency; this release does not provide an offline web bundle. The static collector still uses socket-inactivity timeouts, so a slowly streaming response can exceed its run deadline and is marked incomplete.

## Rollout

1. Maintainer: require all PR CI checks to pass on the final commit, including the clean wheel matrix.
2. Merge the release PR to `main`; GitHub Pages publishes the checked-in `docs/` directory.
3. Verify both published pages, navigation, filters/export and freshness labels. Confirm archived observation dates remain unchanged.
4. Publish tag/release `v2.0.0` with the checked wheel and source archive. Install with `pip install <wheel-path>`; this repository release does not imply a PyPI publication.
5. Operators: back up existing databases, upgrade, run a bounded collection, inspect its manifest and compare two newly archived runs. Exit 2 means partial evidence, not successful complete collection.

## Rollback

If migration fails, comparisons fabricate changes, reports lose unknown-price semantics, or the published dashboard fails its navigation/export checks, stop rollout. Revert the release merge for Pages/code and restore the pre-upgrade database backup before using the previous application. Retain new run manifests and the upgraded database separately for investigation; do not overwrite them with the backup. Withdraw the release recommendation until the failed check is fixed.

## Communication

- **Portfolio visitors:** the README and demo explain that this is an archived snapshot and link to both views.
- **Library users:** the GitHub release notes announce the result-object API, nullable prices and comparison semantics at publication.
- **Maintainers/operators:** this packet records backup, validation and rollback steps before upgrade. No separate messages are sent automatically.

## Decision

**GO WITH CONDITIONS:** publish only after the final commit's CI matrix passes and the Pages deployment is verified. Migration requires a database backup; the historical demo must retain its archived label.
