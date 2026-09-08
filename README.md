# 🛒 Web Scraping Portfolio Project

<p align="center">
  <img src="assets/project_logo.png" alt="ScrapingStore Logo" width="600"/>
</p>

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Pandas](https://img.shields.io/badge/Pandas-Data%20Analysis-150458?logo=pandas)
![Chart.js](https://img.shields.io/badge/Chart.js-Visualization-FF6384?logo=chartdotjs)

A product observation pipeline with a searchable dashboard, immutable collection history, and evidence-aware change reports. Built with Python, Playwright, SQLModel and SQLite; exports CSV for Power BI.

Version **2.0.0** adds saved-run comparisons and visible observation freshness. [Release and migration notes](RELEASE.md) explain the library API changes and legacy database upgrade.

### 🚀 **[Snapshot Demo](https://tzii.github.io/ScrapingStore/)** | **[Terminal View](https://tzii.github.io/ScrapingStore/dashboard_terminal.html)**

The demo preserves 3,000 archived observations from December 2025. It demonstrates the interface, not current market prices or stock. Both themes display the age of that evidence.

## 📸 Dashboard Preview

![Modern Dashboard](assets/dashboard_modern.png)

> **Made by Simone** — Student Project

---

## ✨ Features & Skills Demonstrated

| Category | Technologies & Techniques |
|----------|---------------------------|
| **Web Scraping** | Playwright (headless browser), BeautifulSoup, async/await, pagination handling |
| **Data Cleaning** | Normalization, missing-value provenance, source identity deduplication |
| **Visualization** | Chart.js, Grid.js, Alpine.js, Jinja2 HTML dashboards (modern + terminal) |
| **Database** | SQLModel ORM, SQLite, upsert logic |
| **Data Export** | Power BI-ready CSV (UTF-8 BOM), automated pipeline |
| **DevOps** | Docker, GitHub Actions, GitLab CI, pre-commit hooks, pytest |

---

## 🏗️ Architecture

```mermaid
graph TD
    User[User] --> CLI[CLI (main.py)]
    CLI --> Scraper[Scraper Module]
    Scraper -->|Structured Products| Cleaner[Cleaner Module]
    Cleaner -->|Validated Products| DB[Database (SQLModel)]
    DB -->|Query| Dashboard[Dashboard Generator]
    DB -->|Export| CSV[CSV File]
    Dashboard -->|HTML| Browser[Browser View]
```

---

## 🎯 Project Overview

This project scrapes product data from the [Oxylabs Sandbox E-commerce](https://sandbox.oxylabs.io/products) website and processes it through a complete data pipeline:

1. **Web Scraping** - Extract ~3000 products using Playwright browser automation
2. **Data Cleaning** - Normalize and deduplicate data with Pandas
3. **Visualization** - Interactive dashboards with Chart.js and Grid.js
4. **Power BI Export** - Generate analysis-ready CSV files

---

## 📁 Project Structure

```
ScrapingStore/
├── scraper/
│   ├── __init__.py
│   ├── base.py                     # Abstract base scraper class
│   ├── product_scraper.py          # BeautifulSoup scraper (static HTML)
│   └── product_scraper_browser.py  # Playwright scraper (JS-rendered pages)
├── cleaning/
│   ├── __init__.py
│   └── data_cleaner.py             # Pandas data cleaning pipeline
├── visualization/
│   ├── __init__.py
│   ├── dashboard_generator.py      # Modern dashboard (Tailwind/Chart.js)
│   ├── terminal_dashboard_generator.py  # Retro terminal dashboard
│   └── templates/                  # Jinja2 HTML templates
├── tests/                          # pytest test suite
│   ├── conftest.py                 # Shared fixtures
│   ├── test_scraper.py
│   ├── test_cleaner.py
│   ├── test_database.py
│   ├── test_models.py
│   └── test_cli.py
├── data/                           # Output directory (gitignored)
├── config.py                       # Centralized configuration
├── database.py                     # SQLModel database manager
├── models.py                       # Pydantic/SQLModel data models with validation
├── logger.py                       # Logging configuration (Rich)
├── main.py                         # CLI pipeline orchestrator (Typer)
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- pip package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/tzii/ScrapingStore.git
cd ScrapingStore

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install .

# Install development tools instead
pip install -r requirements-dev.txt

# Install Playwright browsers
playwright install chromium
```

### Running the Pipeline

The browser scraper is the default, including in Docker, and supports JavaScript-rendered content. Install Chromium as shown above. The current sandbox also exposes product markup in its HTML; use `--type static` explicitly for server-rendered pages or fixtures.

```bash
# Quick test: scrape 2 pages with the browser (~64 products)
python main.py scrape --type browser --pages 2

# Default: scrape 10 pages (~320 products)
python main.py scrape

# Scrape all pages (~3000 products)
python main.py scrape --all

# Custom delay between requests (be respectful!)
python main.py scrape --pages 10 --delay 2.0

# Explicit browser selection (also the default)
python main.py scrape --type browser --pages 5

# Show available commands without starting a scrape
python main.py
```

### Other Commands

```bash
# Export existing data to Power BI CSV
python main.py export

# Regenerate dashboards from existing data
python main.py generate-report

# Regenerate the GitHub Pages site in docs/
python main.py generate-report --docs
```

### Configuration

You can configure the scraper using a `.env` file (copy from `.env.example`):

```bash
BASE_URL="https://sandbox.oxylabs.io/products"
MAX_RETRIES=3
DEFAULT_TIMEOUT=30
DB_NAME="products.db"
# Optional output locations (default: ./data and ./docs)
SCRAPINGSTORE_HOME="/path/to/workspace"
DATA_DIR="/path/to/data"
DOCS_DIR="/path/to/docs"
```

### Report scope and catalog search

Both reports describe the **current stored catalog**, selected once after persistence, including previously stored products. An empty scrape does not switch the report to a different dataset. The report-generation timestamp is shared by both views; it is not a collection timestamp or a guarantee that collection was complete.

In the modern report, search (product name, formatted price or availability), availability and inclusive price bounds form one catalog query. The table and CSV export use that query. Export includes **all matching rows across all pages**. Reset clears the whole query. Summaries, charts and insights always describe the full stored catalog and are labelled accordingly.

Both themes share price statistics and histogram bins. Zero prices are included, an even median averages the two middle values, and the last histogram bin includes its upper boundary. Only usable EUR prices contribute to price summaries. Unknown prices remain blank in CSV and appear as “Price unavailable” in the catalog. With a price bound selected, records without a usable EUR price are excluded; without bounds they remain searchable and exportable.

Navigation links follow the generated output paths: local `data/dashboard.html`, GitHub Pages `docs/index.html`, or configured output directories. Programmatic callers with custom filenames can pass `terminal_path` to `generate_dashboard` and `dashboard_path` to `generate_terminal_dashboard`.

### Collection outcomes and publication

Every collection returns a `ScrapeRunResult` containing products, per-page outcomes, errors, retry attempts, HTTP statuses, scope, UTC timestamps and the reason it stopped. The CLI persists the manifest in SQLite and `data/runs/<run-id>.json`.

| Outcome | Meaning | CLI exit | Automatic CSV/reports |
|---------|---------|----------|-----------------------|
| `complete` | Requested scope processed successfully | 0 | Generated |
| `empty` | Successful collection with no products | 0 | Reports generated; an empty catalog does not produce a CSV |
| `partial` | Some useful pages, but failures, rejected cards, identity conflicts or a budget stop | 2 | Only with `--allow-partial` |
| `failed` | No page processed successfully | 1 | Skipped |
| `cancelled` | User interrupted collection | 130 | Skipped |

Valid observations from partial collections are saved. `--allow-partial` keeps exit code 2 and the warning; it does not relabel the run complete. Existing report files remain untouched when automatic publication is skipped. Manual `generate-report` renders the stored catalog with the latest collection status, including failures. CSV exports include price status, source identity, last observed run and UTC collection time; an adjacent `.manifest.json` identifies the catalog scope and latest collection.

```bash
python main.py scrape --pages 5
python main.py scrape --all --page-budget 200 --run-timeout 1800
python main.py scrape --pages 5 --allow-partial
```

`complete` means complete for the requested scope, not necessarily the entire source. A two-page sample cannot establish that unseen products are unavailable. Historical catalog rows remain until explicitly managed.

HTTP 429 and selected transient server/transport errors receive bounded retries, with `Retry-After` and a deadline. HTTP access denials and unrecognized layouts are failures, not empty pages. The adapter confirms an empty catalog using the source's explicit empty message, and recognizes a disabled Next link as the source end. Repeated pages, three consecutive failed pages, the page budget and the deadline stop collection. Speculative page requests beyond a confirmed source end remain in the manifest as `outside_scope`; they do not change the in-scope result or add products to it. Browser concurrency is three; `--delay` is a delay **between batches**, not a minimum spacing between individual requests.

Library callers now use `scraper.scrape(...).products` and inspect `.status`/`.manifest()`. Inside an event loop, use `await browser_scraper.scrape_async(...)`; the synchronous wrapper does not block an existing loop. Caller-owned static scrapers and database managers expose `close()`; the CLI closes its resources.

### Price evidence, identity and existing databases

Both acquisition methods share the source adapter. Prices come from dedicated current-price elements, not the first euro amount in a card description. The EUR parser accepts two-decimal values with comma or dot decimals, grouped thousands, and a leading or trailing currency marker. Negative values, ambiguous multiple prices and unsupported formats retain their original text and a parsing status with `price = null`. A literal zero remains a known price. Numeric prices are still stored as floats; raw source text is retained.

Availability comes from an explicit stock element or enabled purchase control. Contradictory signals produce `Unknown` with a reason. A missing or disabled control alone does not establish that a product is out of stock.

Products use a source-native ID or a detail URL, preserving variant query parameters. SQLite enforces unique source keys and performs atomic upserts. A rename updates the same identity; equal names with different identities survive. Records without a stable identity receive a weak key and remain separate, including across runs. Their counts are reported in the manifest; they cannot support reliable change comparisons.

When an older SQLite database is first opened, the application migrates its catalog in a transaction and keeps the original table as **`product_legacy_v1`**. Historical zero values become `legacy_unknown` with a null price because their original meaning cannot be recovered. Legacy rows retain their IDs and are not automatically matched to newly collected products by name; they can coexist with newly identified records. Back up the database before manual legacy reconciliation. The migration refuses to overwrite an existing backup table.

### Saved runs and observation history

New collections save their accepted product observations, run manifest, and catalog updates in one SQLite transaction. Each observation retains its collected time, identity, raw price and availability signals, parsing status, and parser version. Later price changes or renames update the current catalog without rewriting earlier observations. The catalog retains the newest observation by collected time, even if an older run finishes later. An exact retry does not change the catalog; different evidence submitted under an existing run ID is rejected. A rejected retry writes a separate attempt manifest without overwriting the original JSON sidecar.

```bash
# Find saved run IDs and their outcomes
python main.py runs --limit 10

# Inspect page outcomes, failures, scope, counts and stop reason
python main.py inspect-run RUN_ID

# Include the original product values and parsing evidence as JSON
python main.py inspect-run RUN_ID --products

# Compare the accepted observations in two saved runs
scrapingstore compare-runs OLD_RUN_ID NEW_RUN_ID > comparison.json

# Regenerate both dashboard themes from that run's accepted observations
python main.py generate-report --run-id RUN_ID
```

The selected-run report uses the usual output paths and labels its scope and collection status. An empty saved run generates an empty report, even when the current catalog contains products. A partial run remains labelled partial. Report generation time is separate from each product's collection time. Without `--run-id`, reports continue to show the current stored catalog. Catalog reports and exports read product values and the latest-run metadata from one database snapshot, including during concurrent collections.

History begins with collections saved by this version. Existing catalogs and manifest-only runs remain readable, but cannot be reconstructed as historical reports. The migration adds the history table without inventing past observations. Raw page archives remain future work. Missing a product in a run does not mark it unavailable.

`compare-runs OLD NEW` emits JSON in the supplied direction. Stable source IDs or detail URLs match observations; weak and legacy identities are counted as excluded. Name, availability and price evidence changes include their old and new values. Price deltas use the same known currency on both sides; unknown prices and currency changes have null deltas. A known zero remains zero, and a change from zero has no percentage. `only_in_old` and `only_in_new` mean one-sided observations, never product removal, introduction or stock transitions. Run manifests and warnings retain partial outcomes and differing scopes. Missing or manifest-only runs fail clearly; an empty archived run is valid.

### Observation freshness

Both themes count observations within seven days, over seven days old, and without a recorded time. Future timestamps are flagged separately. Ages are calculated in UTC **at report generation**, including when replaying a historical run; they do not keep ticking in the saved HTML. The modern catalog shows each observation time and freshness label, and its CSV includes `freshness` and `observed_age_days`. These indicators never change the last observed availability. Regenerate the report to update its age assessment.

To refresh the archived showcase with the current templates while preserving its collection times, run `python -m scripts.refresh_demo` from the repository root. To replace it with a newly collected catalog, use `scrapingstore generate-report --docs` after a successful collection.

The browser collector enforces a wall-clock collection deadline. Static Requests timeouts bound socket inactivity: a slowly streaming response may return after the configured run deadline. Its evidence is retained and the run is marked incomplete rather than reported as successful completion.

### Running Tests

```bash
pytest

# With coverage report
pytest --cov=scraper --cov=cleaning --cov=visualization --cov-report=term-missing
```

Browser regressions require Node.js/npm and Playwright Chromium:

```bash
pip install -r requirements-dev.txt
npm ci --ignore-scripts
python -m playwright install chromium
pytest --run-browser
```

The browser tests serve pinned Alpine.js, Grid.js and Chart.js dependencies locally, intercept external requests, and test the generated reports with fixture data. They cover combined search/filter/export, pagination, reset, empty results, zero prices, hostile-looking text and navigation in both directions. These are behavior tests; the Tailwind CDN styling is not exercised. CI installs Chromium and runs them explicitly; plain `pytest` skips browser tests.

---

## 📊 Output Files

| File | Description |
|------|-------------|
| `data/products_powerbi.csv` | Power BI-ready export (UTF-8 BOM) |
| `data/dashboard.html` | Interactive modern dashboard |
| `data/dashboard_terminal.html` | Terminal-style dashboard |
| `docs/index.html` | GitHub Pages modern dashboard (`--docs`) |
| `docs/dashboard_terminal.html` | GitHub Pages terminal dashboard (`--docs`) |

---

## 🔧 Module Details

### Web Scraper (`scraper/`)

- **Two scraper implementations**: Static (BeautifulSoup) and Browser (Playwright)
- Structured data extraction (price, availability, images) at scrape time
- Async/await with concurrency limiting (semaphore) for browser scraper
- Rate limiting and configurable delay between requests
- Pagination with confirmed end signals and hard budgets
- Bounded retries, page outcomes and explicit stop reasons for both scrapers

### Data Cleaner (`cleaning/data_cleaner.py`)

- Availability normalization with explicit unknown/conflicting states
- Deduplication by source identity, with conflicting observations reported
- Name whitespace trimming and preservation of missing prices and raw evidence

### Visualization (`visualization/`)

- **Modern Dashboard**: Tailwind CSS glass UI with aurora backdrop, Chart.js (price histogram, availability doughnut), Grid.js table with search, sorting, availability/price-range filters and client-side CSV export, top-10 price leaderboard, animated KPI counters, Alpine.js dark/light mode (system-aware, persisted), reduced-motion and aria support
- **Terminal Dashboard**: Retro CRT-style with ASCII bar charts, auto-calculated KPIs
- Auto-detected franchise/keyword analysis (no hardcoded keywords)

### Data Models (`models.py`)

- SQLModel/Pydantic hybrid with model validation
- Price must be finite and non-negative; name must not be empty
- Automatic UTC timestamps on creation

#### Terminal Dashboard Mode
The project also includes a retro-style terminal dashboard for CLI enthusiasts:

![Terminal Dashboard](assets/dashboard_terminal.png)

---

## 📈 Power BI Integration

The `products_powerbi.csv` file is formatted for seamless Power BI import:

1. Open Power BI Desktop
2. Click **Get Data** → **Text/CSV**
3. Select `data/products_powerbi.csv`
4. Data types will be auto-detected

---

## 🤝 Responsible Scraping

This project targets a public scraping sandbox explicitly intended for practice. When adapting it to other sites:

- **Check `robots.txt` and the site's Terms of Service** before scraping
- **Keep a delay between requests** (`--delay`, default 1s) and do not raise the browser concurrency limit
- **Identify your client honestly** via the `USER_AGENT` env var where appropriate
- **Never scrape private, personal, or paywalled data**, and never bypass authentication or captchas
- **Fail gracefully**: both scrapers back off and stop after repeated failures instead of hammering the server

---

## ⚠️ Known Limitations

- **Source rendering**: The browser scraper supports JavaScript. Static scraping can only use markup supplied in the HTTP response; it cannot wait for client-rendered cards.
- **Weak and legacy identities**: Records without a stable source identity are preserved separately. They are not suitable for reliable price-history comparisons.
- **Sandbox-specific**: The CSS selectors (`div.product-card`, `h4`) are tailored to the Oxylabs sandbox. Adapting to a different site would require updating the selectors.

---

## 🛠️ Technologies

- **Python 3.9+**
- **Playwright** - Browser automation for JS-rendered sites
- **BeautifulSoup4** - HTML parsing
- **Requests** - HTTP client
- **Pandas** - Report statistics and CSV export
- **SQLModel / Pydantic** - ORM and data validation
- **Typer / Rich** - CLI interface
- **Chart.js / Grid.js / Alpine.js** - Frontend visualization
- **Jinja2** - HTML templating
- **Docker** - Containerization
- **GitHub Actions** - CI/CD

---

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>Made by Simone</b> • Student Project • 2026
</p>
