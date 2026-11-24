"""ScrapingStore: collect product prices and stock across runs and report what changed."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("scrapingstore")
except PackageNotFoundError:
    __version__ = "3.0.0"

PARSER_VERSION = "3.0"

__all__ = ["__version__", "PARSER_VERSION"]
