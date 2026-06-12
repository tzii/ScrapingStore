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
