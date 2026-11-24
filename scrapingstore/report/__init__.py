"""Offline HTML report: snapshot, product x run timeline, and columnar serializer."""

from scrapingstore.report.columnar import decode_columnar, encode_columnar
from scrapingstore.report.generator import generate_dashboard, render_report
from scrapingstore.report.snapshot import ReportSnapshot
from scrapingstore.report.timeline import build_timeline

__all__ = [
    "ReportSnapshot",
    "build_timeline",
    "decode_columnar",
    "encode_columnar",
    "generate_dashboard",
    "render_report",
]
