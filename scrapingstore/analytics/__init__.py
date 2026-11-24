"""Analytics: exact directional diffs, TF-IDF franchises, price ladders, censored restocks."""

from scrapingstore.analytics.comparison import compare_observations, format_diff_summary
from scrapingstore.analytics.insights import (
    availability_stats,
    censored_restock_analysis,
    detect_franchises_tfidf,
    detect_possibly_delisted,
    genre_breakdown,
    observation_period,
    price_histogram,
    price_ladder,
    price_statistics,
)

__all__ = [
    "availability_stats",
    "censored_restock_analysis",
    "compare_observations",
    "detect_franchises_tfidf",
    "detect_possibly_delisted",
    "format_diff_summary",
    "genre_breakdown",
    "observation_period",
    "price_histogram",
    "price_ladder",
    "price_statistics",
]
