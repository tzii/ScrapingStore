"""Compatibility shim re-exporting scrapingstore.transport.collector & rate_limit."""

from scrapingstore.transport.collector import BaseScraper
from scrapingstore.transport.rate_limit import TRANSIENT_STATUSES, retry_delay

__all__ = ["BaseScraper", "TRANSIENT_STATUSES", "retry_delay"]
