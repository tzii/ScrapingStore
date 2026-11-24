"""Compatibility shim re-exporting scrapingstore.sources.oxylabs & base."""

from scrapingstore.sources.base import ParsedPrice, availability_signal, parse_price
from scrapingstore.sources.oxylabs import (
    CARD_SELECTOR,
    EMPTY_TEXT,
    READY_SELECTOR,
    extract_price,
    parse_card,
    parse_page,
)

__all__ = [
    "CARD_SELECTOR",
    "EMPTY_TEXT",
    "ParsedPrice",
    "READY_SELECTOR",
    "availability_signal",
    "extract_price",
    "parse_card",
    "parse_page",
    "parse_price",
]
