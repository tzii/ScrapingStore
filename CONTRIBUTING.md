# Contributing to ScrapingStore

Thank you for your interest in contributing!

## Code Style
- We use `black` for formatting.
- We use `flake8` for linting.
- We use `mypy` for static type checking.

## Development Setup
1. Create and activate a virtual environment.
2. Install development dependencies: `pip install -r requirements-dev.txt`.
3. Install the package locally: `pip install --no-deps -e .`.

## Pull Requests
1. Fork the repo.
2. Create a feature branch.
3. Make your changes.
4. Run tests: `pytest --cov`.
5. Run checks: `black --check .`, `flake8 .`, and `mypy cleaning scraper visualization *.py`.
6. Run linting: `pre-commit run --all-files`.
7. Submit a PR.

Browser regressions require `npm ci --ignore-scripts` and `python -m playwright install chromium`; run `pytest --run-browser --cov` before release. CI also builds source and wheel distributions and exercises the wheel in fresh environments outside the checkout. The smoke script is `scripts/wheel_smoke.py`; run it only after installing the wheel into a clean environment.

Use `python -m scripts.refresh_demo` to update the checked-in showcase from its archived observations. Preserve timestamps and collection provenance; do not describe the archived data as a live collection.
