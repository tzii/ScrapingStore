"""Compatibility shim re-exporting scrapingstore.ledger.database."""

from scrapingstore.ledger.database import HISTORY_VERSION, DatabaseManager

__all__ = ["DatabaseManager", "HISTORY_VERSION"]
