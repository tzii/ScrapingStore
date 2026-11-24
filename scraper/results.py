"""Compatibility shim re-exporting scrapingstore.sources.results."""

from scrapingstore import PARSER_VERSION
from scrapingstore.io_utils import utc_now
from scrapingstore.sources.results import PageResult, ScrapeRunResult

__all__ = ["PARSER_VERSION", "PageResult", "ScrapeRunResult", "utc_now"]
