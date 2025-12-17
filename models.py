"""
Data Models
===========
SQLModel definitions for the application.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    """
    Product model representing a scraped item.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    price: float = Field(default=0.0)
    currency: str = Field(default="EUR")
    availability: str = Field(default="Unknown")
    image_url: Optional[str] = None
    source_url: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Optional metadata
    category: Optional[str] = None
    rating: Optional[float] = None
