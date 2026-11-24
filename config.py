"""Compatibility shim re-exporting scrapingstore.config (lazy, zero import side effects)."""

from scrapingstore.config import (
    DEFAULT_BASE_URL,
    DEFAULT_USER_AGENT,
    Settings,
    _env_float,
    _env_int,
    get_settings,
)

_s = get_settings()
BASE_DIR = _s.package_dir.parent
PROJECT_DIR = _s.project_dir
DATA_DIR = _s.data_dir
DOCS_DIR = _s.docs_dir
TEMPLATES_DIR = _s.templates_dir
DB_NAME = _s.db_name
DB_PATH = _s.db_path
DB_URL = _s.db_url
CSV_POWERBI_PATH = _s.csv_powerbi_path
DASHBOARD_HTML_PATH = _s.dashboard_html_path
DOCS_DASHBOARD_HTML_PATH = _s.docs_dashboard_html_path
# The terminal-style report was removed in 3.0; these paths are kept for old imports.
TERMINAL_DASHBOARD_HTML_PATH = _s.data_dir / "dashboard_terminal.html"
DOCS_TERMINAL_DASHBOARD_HTML_PATH = _s.docs_dir / "dashboard_terminal.html"
BASE_URL = _s.base_url
DEFAULT_TIMEOUT = _s.default_timeout
MAX_RETRIES = _s.max_retries
RETRY_BACKOFF = _s.retry_backoff
USER_AGENT_FALLBACK = _s.user_agent

__all__ = [
    "BASE_DIR",
    "BASE_URL",
    "CSV_POWERBI_PATH",
    "DASHBOARD_HTML_PATH",
    "DATA_DIR",
    "DB_NAME",
    "DB_PATH",
    "DB_URL",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_USER_AGENT",
    "DOCS_DASHBOARD_HTML_PATH",
    "DOCS_DIR",
    "DOCS_TERMINAL_DASHBOARD_HTML_PATH",
    "MAX_RETRIES",
    "PROJECT_DIR",
    "RETRY_BACKOFF",
    "Settings",
    "TEMPLATES_DIR",
    "TERMINAL_DASHBOARD_HTML_PATH",
    "USER_AGENT_FALLBACK",
    "_env_float",
    "_env_int",
    "get_settings",
]
