"""Compatibility shim re-exporting scrapingstore.logger."""

from scrapingstore.logger import get_logger, setup_logger

__all__ = ["get_logger", "setup_logger"]
