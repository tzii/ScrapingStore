"""Side-effect-free, cwd-aware configuration for ScrapingStore."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv

from scrapingstore import __version__

logger = logging.getLogger("scrapingstore.config")

DEFAULT_BASE_URL = "https://sandbox.oxylabs.io/products"
DEFAULT_USER_AGENT = (
    f"ScrapingStore/{__version__} (+https://github.com/tzii/ScrapingStore)"
)

_dotenv_loaded = False


def load_workspace_dotenv(*, force: bool = False) -> Optional[str]:
    """Load .env starting from the current working directory (safe for wheel installs)."""
    global _dotenv_loaded
    if _dotenv_loaded and not force:
        return None
    _dotenv_loaded = True
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)
        return env_path
    return None


def _env_int(name: str, default: int) -> int:
    """Read an integer env var, logging a warning on invalid input."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer for %s=%r; falling back to default %s",
            name,
            raw,
            default,
        )
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float env var, logging a warning on invalid input."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid float for %s=%r; falling back to default %s",
            name,
            raw,
            default,
        )
        return default


@dataclass(frozen=True)
class Settings:
    """Resolved workspace and pipeline configuration (created lazily, no FS writes)."""

    package_dir: Path
    project_dir: Path
    data_dir: Path
    docs_dir: Path
    templates_dir: Path
    db_name: str
    db_path: Path
    db_url: str
    csv_powerbi_path: Path
    dashboard_html_path: Path
    docs_dashboard_html_path: Path
    base_url: str
    default_timeout: int
    max_retries: int
    retry_backoff: float
    user_agent: str
    respect_robots: bool

    @classmethod
    def from_env(cls, *, load_env: bool = True) -> "Settings":
        if load_env:
            load_workspace_dotenv()
        package_dir = Path(__file__).resolve().parent
        project_dir = (
            Path(os.getenv("SCRAPINGSTORE_HOME", str(Path.cwd())))
            .expanduser()
            .resolve()
        )
        data_dir = (
            Path(os.getenv("DATA_DIR", str(project_dir / "data")))
            .expanduser()
            .resolve()
        )
        docs_dir = (
            Path(os.getenv("DOCS_DIR", str(project_dir / "docs")))
            .expanduser()
            .resolve()
        )
        templates_dir = package_dir / "report" / "templates"
        db_name = os.getenv("DB_NAME", "products.db")
        db_path = data_dir / db_name
        db_url = os.getenv("DB_URL", f"sqlite:///{db_path}")
        respect_robots = os.getenv("RESPECT_ROBOTS", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        return cls(
            package_dir=package_dir,
            project_dir=project_dir,
            data_dir=data_dir,
            docs_dir=docs_dir,
            templates_dir=templates_dir,
            db_name=db_name,
            db_path=db_path,
            db_url=db_url,
            csv_powerbi_path=data_dir / "products_powerbi.csv",
            dashboard_html_path=data_dir / "dashboard.html",
            docs_dashboard_html_path=docs_dir / "index.html",
            base_url=os.getenv("BASE_URL", DEFAULT_BASE_URL),
            default_timeout=_env_int("DEFAULT_TIMEOUT", 30),
            max_retries=_env_int("MAX_RETRIES", 3),
            retry_backoff=_env_float("RETRY_BACKOFF", 0.5),
            user_agent=os.getenv("USER_AGENT", DEFAULT_USER_AGENT),
            respect_robots=respect_robots,
        )


def get_settings(*, load_env: bool = True) -> Settings:
    """Resolve current settings from environment without mutating the filesystem."""
    return Settings.from_env(load_env=load_env)
