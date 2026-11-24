"""Pluggable source adapters, parsing contracts, and deterministic mock market."""

from scrapingstore.sources.base import (
    ParsedPrice,
    SourceAdapter,
    availability_signal,
    extract_image_url,
    infer_genre_from_image_url,
    parse_price,
)
from scrapingstore.sources.mock_market import MockMarket, MockMarketAdapter
from scrapingstore.sources.oxylabs import OxylabsAdapter, parse_card, parse_page
from scrapingstore.sources.recipe import JsonLdAdapter, RecipeAdapter
from scrapingstore.sources.results import PageResult, ScrapeRunResult, clean_products

__all__ = [
    "JsonLdAdapter",
    "MockMarket",
    "MockMarketAdapter",
    "OxylabsAdapter",
    "PageResult",
    "ParsedPrice",
    "RecipeAdapter",
    "ScrapeRunResult",
    "SourceAdapter",
    "availability_signal",
    "clean_products",
    "extract_image_url",
    "infer_genre_from_image_url",
    "parse_card",
    "parse_page",
    "parse_price",
]
