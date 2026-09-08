"""Collection outcomes that survive acquisition, persistence and reporting."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from models import Product

PARSER_VERSION = "2.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    def manifest(self) -> Dict[str, Any]:
        return {
            "page": self.number,
            "url": self.url,
            "status": self.status,
            "products": len(self.products),
            "rejected_cards": self.rejected_cards,
            "attempts": self.attempts,
            "http_status": self.http_status,
            "source_end": self.source_end,
            "outside_scope": self.outside_scope,
            "errors": self.errors,
        }


@dataclass
class ScrapeRunResult:
    source_url: str
    requested_pages: Optional[int]
    scraper_type: str
    run_id: str = field(default_factory=lambda: str(uuid4()))
    pages: List[PageResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    stop_reason: str = "running"
    accepted_products: int = 0
    configuration: Dict[str, Any] = field(default_factory=dict)

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
        return {
            "run_id": self.run_id,
            "status": self.status,
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
            "errors": self.errors,
            "configuration": self.configuration,
            "pages": [p.manifest() for p in sorted(self.pages, key=lambda p: p.number)],
        }
