"""Quality gates, parser drift sentinels, and automatic Data Forensics (smells)."""

from scrapingstore.quality.gates import evaluate_quality_gate, field_coverage
from scrapingstore.quality.smells import DataSmell, detect_smells, ks_statistic

__all__ = [
    "DataSmell",
    "detect_smells",
    "evaluate_quality_gate",
    "field_coverage",
    "ks_statistic",
]
