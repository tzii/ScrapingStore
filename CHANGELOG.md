# Changelog

All notable changes to this project will be documented in this file.

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
