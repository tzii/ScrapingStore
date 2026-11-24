# Reference: CLI, Configuration, Recipes & Testing

## CLI Commands

All commands accept short run prefixes (e.g. `a1b2c3d4`) as well as `@latest`, `@prev`, and `@~N`.

| Command | Alias | Description |
|---|---|---|
| `scrapingstore scrape` | `collect` | Collect observations (`--type auto\|static\|browser`, `--source oxylabs\|jsonld\|mock`, `--recipe`, `--pages`, `--all`, `--delay`, `--allow-partial`, `--json-progress`) |
| `scrapingstore demo` | — | Collect a simulated store 2 to 5 times and build its report (`--epochs`, `--docs`, `--open`) |
| `scrapingstore runs` | `log` | List archived runs newest-first (`--limit`, `--plain`) |
| `scrapingstore inspect-run [RUN]` | `show` | Print run manifest and optional `--products` as JSON |
| `scrapingstore diff [OLD] [NEW]` | — | Human-readable diff (defaults to `@prev..@latest`; `--json` for raw output) |
| `scrapingstore compare-runs [OLD] [NEW]` | — | Strict directional JSON comparison |
| `scrapingstore blame <SKU>` | — | Show which run last changed each field of a product (`--json`) |
| `scrapingstore reparse [RUN]` | — | Replay archived raw HTML through current parser (`--apply` to persist) |
| `scrapingstore smells` | — | Check the catalog or a run for data problems (`--run-id`, `--strict`, `--json`) |
| `scrapingstore doctor` | — | Audit environment, Chromium, SQLite ledger, and optional `--probe` on page 1 |
| `scrapingstore generate-report` | `report` | Build the offline HTML report (`--docs`, `--run-id`, `--history-runs`, `--open`) |
| `scrapingstore export` | — | Export formula-safe Power BI UTF-8 BOM CSV + atomic `.manifest.json` |
| `scrapingstore serve` | — | Serve the report locally; each page load rebuilds it from saved data (`--host`, `--port`, `--open`) |
| `scrapingstore tui` | — | Browse saved data in an interactive terminal shell |

### Exit Codes

| Exit | Meaning |
|---|---|
| `0` | `complete` or `empty` run |
| `1` | `failed` run, persistence error, or invalid argument |
| `2` | `partial` run (or `--strict` smells error) |
| `3` | `degraded` run (quality gate blocked silent parser drift) |
| `130` | `cancelled` by user interrupt |

---

## Configuration (`.env` / Environment Variables)

Configuration is lazy (zero side effects on import) and loads `.env` from the current working directory (`find_dotenv(usecwd=True)`). Invalid numeric values emit a warning before falling back to defaults.

```bash
BASE_URL="https://sandbox.oxylabs.io/products"
USER_AGENT="ScrapingStore/3.0.0 (+https://github.com/tzii/ScrapingStore)"
MAX_RETRIES=3
RETRY_BACKOFF=0.5
DEFAULT_TIMEOUT=30
RESPECT_ROBOTS=1
DB_NAME="products.db"
SCRAPINGSTORE_HOME="/path/to/workspace"
DATA_DIR="/path/to/data"
DOCS_DIR="/path/to/docs"
```

---

## Declarative Store Recipes (TOML)

Scrape any static or rendered storefront without writing Python:

```toml
[recipe]
name = "acme-books"
card_selector = "article.product_pod"
title_selector = "h3 a"
price_selector = ".price_color"
availability_selector = ".availability"
link_selector = "h3 a"
category_selector = ".genre"
next_selector = "li.next a"
currencies = ["EUR", "GBP", "USD"]
```

Run with:

```bash
scrapingstore scrape --recipe acme.toml --url https://store.example/catalog --pages 5
```

For sites embedding Schema.org `<script type="application/ld+json">` Product markup, use `--source jsonld` directly.

---

## Docker

```bash
docker build -t scrapingstore .
docker run --rm -v "$(pwd)/data:/app/data" scrapingstore demo
```

The container runs as a non-root `scraper` user with `.dockerignore` excluding local artifacts and `ENTRYPOINT ["scrapingstore"]`.

---

## Testing & Quality

```bash
pip install -e ".[dev]"
ruff check scrapingstore tests scripts
mypy scrapingstore
pytest
pytest --run-browser   # Real Chromium tests against the offline HTML report
```
