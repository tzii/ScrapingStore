"""Collection outcomes, per-page telemetry, and identity-safe normalization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from scrapingstore import PARSER_VERSION
from scrapingstore.io_utils import utc_now
from scrapingstore.ledger.models import Product
from scrapingstore.sources.base import availability_signal


@dataclass
class PageResult:
    number: int
    url: str
    status: str = "failed"
    products: List[Product] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    attempts: int = 1
    http_status: Optional[int] = None
    source_end: bool = False
    outside_scope: bool = False
    fingerprint: Optional[str] = None
    rejected_cards: int = 0
    elapsed_ms: Optional[float] = None
    bytes_received: Optional[int] = None
    raw_html: Optional[bytes] = field(default=None, repr=False)
    raw_blob_sha256: Optional[str] = None

    def set_raw_html(self, content: bytes) -> None:
        self.raw_html = content
        self.bytes_received = len(content)
        self.raw_blob_sha256 = hashlib.sha256(content).hexdigest()

    def manifest(self) -> Dict[str, Any]:
        return {
            "page": self.number,
            "url": self.url,
            "status": self.status,
            "products": len(self.products),
            "rejected_cards": self.rejected_cards,
            "attempts": self.attempts,
            "http_status": self.http_status,
            "elapsed_ms": round(self.elapsed_ms, 2)
            if self.elapsed_ms is not None
            else None,
            "bytes_received": self.bytes_received,
            "source_end": self.source_end,
            "outside_scope": self.outside_scope,
            "fingerprint": self.fingerprint,
            "raw_blob_sha256": self.raw_blob_sha256,
            "errors": self.errors,
        }


@dataclass
class ScrapeRunResult:
    source_url: str
    requested_pages: Optional[int]
    scraper_type: str
    run_id: str = field(default_factory=lambda: str(__import__("uuid").uuid4()))
    source_name: str = "oxylabs"
    pages: List[PageResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    stop_reason: str = "running"
    accepted_products: int = 0
    configuration: Dict[str, Any] = field(default_factory=dict)
    quality_gate: Optional[Dict[str, Any]] = None
    degraded_reasons: List[str] = field(default_factory=list)

    @property
    def short_id(self) -> str:
        clean = self.run_id.replace("-", "")
        return clean[:8] if len(clean) >= 8 else clean

    @property
    def products(self) -> List[Product]:
        return [
            product
            for page in sorted(self.pages, key=lambda p: p.number)
            if not page.outside_scope
            for product in page.products
        ]

    @property
    def relevant_pages(self) -> List[PageResult]:
        return [page for page in self.pages if not page.outside_scope]

    @property
    def raw_pages(self) -> Dict[int, bytes]:
        return {
            page.number: page.raw_html
            for page in self.pages
            if page.raw_html is not None
        }

    @property
    def status(self) -> str:
        if self.stop_reason == "cancelled":
            return "cancelled"
        successful = any(
            page.status in ("success", "empty", "partial")
            for page in self.relevant_pages
        )
        incomplete = (
            bool(self.errors)
            or any(
                p.status in ("failed", "partial") or p.errors
                for p in self.relevant_pages
            )
            or self.stop_reason not in ("page_limit", "source_end")
        )
        if not successful:
            return "failed"
        if incomplete:
            return "partial"
        if self.degraded_reasons:
            return "degraded"
        return "complete" if self.products else "empty"

    def finish(
        self, reason: str, *, allow_source_end: bool = True
    ) -> "ScrapeRunResult":
        ends = [
            page.number
            for page in self.pages
            if page.source_end and page.status in ("success", "empty", "partial")
        ]
        if ends:
            end = min(ends)
            for page in self.pages:
                page.outside_scope = page.number > end
            if allow_source_end and reason in (
                "source_end",
                "page_limit",
                "page_budget",
                "deadline",
            ):
                reason = "source_end"
        self.stop_reason = reason
        self.finished_at = utc_now()
        return self

    def manifest(self) -> Dict[str, Any]:
        products = self.products
        latencies = [
            p.elapsed_ms for p in self.relevant_pages if p.elapsed_ms is not None
        ]
        total_bytes = sum(
            p.bytes_received or 0 for p in self.relevant_pages
        )
        payload: Dict[str, Any] = {
            "run_id": self.run_id,
            "short_id": self.short_id,
            "status": self.status,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "scraper_type": self.scraper_type,
            "scope": {
                "requested_pages": self.requested_pages,
                "description": (
                    "all pages"
                    if self.requested_pages is None
                    else f"first {self.requested_pages} pages"
                ),
            },
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "stop_reason": self.stop_reason,
            "parser_version": PARSER_VERSION,
            "pages_attempted": len(self.pages),
            "pages_succeeded": sum(
                p.status in ("success", "empty") for p in self.relevant_pages
            ),
            "pages_failed": sum(p.status == "failed" for p in self.relevant_pages),
            "pages_partial": sum(p.status == "partial" for p in self.relevant_pages),
            "pages_outside_scope": sum(p.outside_scope for p in self.pages),
            "products_parsed": len(products),
            "products_accepted": self.accepted_products,
            "rejected_cards": sum(p.rejected_cards for p in self.relevant_pages),
            "missing_prices": sum(p.price is None for p in products),
            "weak_identities": sum(p.identity_kind == "weak" for p in products),
            "total_bytes": total_bytes,
            "avg_page_ms": round(sum(latencies) / len(latencies), 2)
            if latencies
            else None,
            "errors": self.errors,
            "degraded_reasons": self.degraded_reasons,
            "configuration": self.configuration,
            "pages": [p.manifest() for p in sorted(self.pages, key=lambda p: p.number)],
        }
        if self.quality_gate is not None:
            payload["quality_gate"] = self.quality_gate
        return payload


def clean_products(
    products: List[Product], warnings: Optional[List[str]] = None
) -> List[Product]:
    """Normalize observations without inventing prices or collapsing distinct identities."""
    cleaned: List[Product] = []
    seen: dict[str, Product] = {}
    for original in products:
        product = Product(**original.model_dump())
        product.availability, reason = availability_signal(product.availability)
        product.availability_reason = product.availability_reason or reason
        previous = seen.get(product.source_key)
        if previous is not None:
            fields = ("name", "price", "currency", "availability", "product_url")
            if any(getattr(previous, key) != getattr(product, key) for key in fields):
                message = (
                    f"Conflicting observations for identity {product.source_key}; "
                    "kept the first"
                )
                if warnings is None:
                    raise ValueError(message)
                warnings.append(message)
            continue
        seen[product.source_key] = product
        cleaned.append(product)
    return cleaned
