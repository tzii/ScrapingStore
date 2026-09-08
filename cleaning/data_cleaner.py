"""Normalize observations without inventing prices or deduplicating by title."""

from typing import List, Optional

from models import Product
from scraper.parsing import availability_signal


def clean_products(
    products: List[Product], warnings: Optional[List[str]] = None
) -> List[Product]:
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
                message = f"Conflicting observations for identity {product.source_key}; kept the first"
                if warnings is None:
                    raise ValueError(message)
                warnings.append(message)
            continue
        seen[product.source_key] = product
        cleaned.append(product)
    return cleaned
