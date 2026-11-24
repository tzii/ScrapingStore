"""SQLModel data models for the ScrapingStore observation ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import Any, Optional
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel

from scrapingstore import PARSER_VERSION


def price_to_minor(value: Optional[float]) -> Optional[int]:
    """Convert a major-unit price to exact integer minor units (e.g. EUR cents)."""
    if value is None:
        return None
    return int(
        (Decimal(str(value)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def minor_to_price(minor: Optional[int]) -> Optional[float]:
    """Convert integer minor units back to major-unit float."""
    if minor is None:
        return None
    return float(Decimal(minor) / Decimal("100"))


class Product(SQLModel, table=True):
    """Current catalog projection of a scraped product with full provenance."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    price: Optional[float] = Field(default=None, nullable=True)
    price_minor: Optional[int] = Field(default=None, nullable=True, index=True)
    price_raw: Optional[str] = None
    price_status: str = "missing"
    currency: str = Field(default="EUR")
    availability: str = Field(default="Unknown")
    availability_raw: Optional[str] = None
    availability_reason: Optional[str] = None
    image_url: Optional[str] = None
    source_url: str
    source_id: Optional[str] = None
    product_url: Optional[str] = None
    source_key: str = Field(
        default_factory=lambda: "weak:" + str(uuid4()), unique=True, index=True
    )
    identity_kind: str = "weak"
    parser_version: str = PARSER_VERSION
    last_run_id: Optional[str] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Metadata extracted from cards or detail enrichment
    category: Optional[str] = None
    rating: Optional[float] = None

    def model_post_init(self, __context: Any) -> None:
        self.__dict__["name"] = self.name.strip()
        if not self.name:
            raise ValueError("Product name must not be empty")

        # Sync float price and integer minor units cleanly.
        if self.price is None and self.price_minor is not None:
            if self.price_minor < 0:
                raise ValueError("Price must be a finite non-negative number")
            self.__dict__["price"] = minor_to_price(self.price_minor)

        if self.price is not None:
            if not isfinite(self.price) or self.price < 0:
                raise ValueError("Price must be a finite non-negative number")
            self.__dict__["price_minor"] = price_to_minor(self.price)
            self.__dict__["price_status"] = "known"
        else:
            self.__dict__["price_minor"] = None
            if self.price_status == "known":
                self.__dict__["price_status"] = "missing"

        if self.source_id:
            self.__dict__["source_key"] = (
                f"{urlsplit(self.source_url).netloc.lower()}:id:{self.source_id}"
            )
            self.__dict__["identity_kind"] = "native"
        elif self.product_url:
            self.__dict__["source_key"] = "url:" + self.product_url
            self.__dict__["identity_kind"] = "url"


class CollectionRun(SQLModel, table=True):
    """Typed run record + full immutable manifest JSON."""

    id: str = Field(primary_key=True)
    short_id: str = Field(default="", index=True)
    started_at: datetime = Field(index=True)
    finished_at: Optional[datetime] = None
    status: str = Field(default="unknown", index=True)
    source_name: str = Field(default="oxylabs")
    scraper_type: str = Field(default="unknown")
    stop_reason: str = Field(default="unknown")
    pages_attempted: int = 0
    pages_succeeded: int = 0
    pages_failed: int = 0
    products_accepted: int = 0
    parser_version: str = PARSER_VERSION
    history_version: int = 0
    manifest_json: str


class RawPageBlob(SQLModel, table=True):
    """Content-addressed gzipped raw HTML archive for time-travel reparsing."""

    sha256: str = Field(primary_key=True)
    content_gz: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    byte_length: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PageRecord(SQLModel, table=True):
    """Per-page acquisition telemetry, outcomes, and link to raw HTML blob."""

    run_id: str = Field(primary_key=True, foreign_key="collectionrun.id")
    page_number: int = Field(primary_key=True)
    url: str
    status: str = "failed"
    http_status: Optional[int] = None
    attempts: int = 1
    products_count: int = 0
    rejected_cards: int = 0
    elapsed_ms: Optional[float] = None
    bytes_received: Optional[int] = None
    source_end: bool = False
    outside_scope: bool = False
    fingerprint: Optional[str] = None
    raw_blob_sha256: Optional[str] = Field(
        default=None, foreign_key="rawpageblob.sha256", index=True
    )
    errors_json: str = "[]"


class ProductObservation(SQLModel, table=True):
    """Immutable, SQL-queryable product evidence captured by one collection run."""

    run_id: str = Field(primary_key=True, foreign_key="collectionrun.id")
    source_key: str = Field(primary_key=True, index=True)
    position: int
    name: str = ""
    price_minor: Optional[int] = Field(default=None, nullable=True, index=True)
    currency: str = "EUR"
    price_status: str = "missing"
    availability: str = "Unknown"
    category: Optional[str] = Field(default=None, index=True)
    rating: Optional[float] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    identity_kind: str = "weak"
    parser_version: str = PARSER_VERSION
    scraped_at: Optional[datetime] = Field(default=None, index=True)
    snapshot_json: str
