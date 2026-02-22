# Changelog

All notable changes to this project will be documented in this file.

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
