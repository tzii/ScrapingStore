"""Compatibility shim re-exporting scrapingstore.transport.http.StaticScraper."""

import time

from scrapingstore.transport.http import StaticScraper

__all__ = ["StaticScraper", "time"]
