"""
Data Models
===========
SQLModel definitions for the application.
"""

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Optional
from urllib.parse import urlsplit
from uuid import uuid4
from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    """
    Product model representing a scraped item.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    price: Optional[float] = Field(default=None, nullable=True)
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
    parser_version: str = "2.0"
    last_run_id: Optional[str] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Optional metadata
    category: Optional[str] = None
    rating: Optional[float] = None

    def model_post_init(self, __context: Any) -> None:
        # Strip and validate name
        # SQLModel attaches ORM state after model_validate; update validated data directly.
        self.__dict__["name"] = self.name.strip()
        if not self.name:
            raise ValueError("Product name must not be empty")
        # Validate price
        if self.price is not None and (not isfinite(self.price) or self.price < 0):
            raise ValueError("Price must be a finite non-negative number")
        if self.price is not None:
            self.__dict__["price_status"] = "known"
        elif self.price_status == "known":
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
    """Persisted run evidence, separate from the current product catalog."""

    id: str = Field(primary_key=True)
    started_at: datetime
    manifest_json: str


class ProductObservation(SQLModel, table=True):
    """Immutable product evidence captured by one collection run."""

    run_id: str = Field(primary_key=True, foreign_key="collectionrun.id")
    source_key: str = Field(primary_key=True)
    position: int
    snapshot_json: str
