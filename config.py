"""
Configuration Settings
======================
Centralized configuration for the scraping pipeline.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _env_int(name: str, default: int) -> int:
    """Read an integer env var, falling back to default on invalid values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to default on invalid values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Base Paths
BASE_DIR = Path(__file__).parent
PROJECT_DIR = Path(os.getenv("SCRAPINGSTORE_HOME", Path.cwd())).expanduser().resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data")).expanduser().resolve()
DOCS_DIR = Path(os.getenv("DOCS_DIR", PROJECT_DIR / "docs")).expanduser().resolve()
ASSETS_DIR = BASE_DIR / "assets"
TEMPLATES_DIR = BASE_DIR / "visualization" / "templates"

# Database
DB_NAME = os.getenv("DB_NAME", "products.db")
DB_PATH = DATA_DIR / DB_NAME
DB_URL = os.getenv("DB_URL", f"sqlite:///{DB_PATH}")

# Output Files
CSV_RAW_PATH = DATA_DIR / "products_raw.csv"
CSV_CLEANED_PATH = DATA_DIR / "products_cleaned.csv"
CSV_POWERBI_PATH = DATA_DIR / "products_powerbi.csv"
DASHBOARD_HTML_PATH = DATA_DIR / "dashboard.html"
TERMINAL_DASHBOARD_HTML_PATH = DATA_DIR / "dashboard_terminal.html"
DOCS_DASHBOARD_HTML_PATH = DOCS_DIR / "index.html"
DOCS_TERMINAL_DASHBOARD_HTML_PATH = DOCS_DIR / "dashboard_terminal.html"

# Scraper Settings
BASE_URL = os.getenv("BASE_URL", "https://sandbox.oxylabs.io/products")
DEFAULT_TIMEOUT = _env_int("DEFAULT_TIMEOUT", 30)
MAX_RETRIES = _env_int("MAX_RETRIES", 3)
RETRY_BACKOFF = _env_float("RETRY_BACKOFF", 0.5)
USER_AGENT_FALLBACK = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
