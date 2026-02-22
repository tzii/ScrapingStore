"""
Data Cleaner Module
===================
Vectorized data cleaning pipeline using Pandas.
"""

from typing import List, Dict, Any, cast
import pandas as pd
import numpy as np
from models import Product
from logger import get_logger

logger = get_logger(__name__)


def clean_products(products: List[Product]) -> List[Product]:
    """
    Clean a list of Product objects using vectorized Pandas operations.

    Handles both pre-extracted data (price/availability already parsed by
    the scraper) and legacy raw data where price may still need extraction.
    """
    if not products:
        return []

    logger.info(f"Cleaning {len(products)} products...")

    df = pd.DataFrame([p.model_dump() for p in products])

    # 1. Ensure price column exists and fill missing values
    if "price" not in df.columns:
        df["price"] = 0.0

    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

    # 2. Normalize availability to standard values
    if "availability" in df.columns:
        text_col = df["availability"].str.lower()
        conditions = [
            text_col.str.contains("in stock|add to basket", na=False),
            text_col.str.contains("out of stock|unavailable", na=False),
        ]
        choices = ["In Stock", "Out of Stock"]
        df["availability"] = np.select(conditions, choices, default="Unknown")
    else:
        df["availability"] = "Unknown"

    # 3. Clean name
    df["name"] = df["name"].str.strip()

    # 4. Deduplicate by name
    initial_count = len(df)
    df.drop_duplicates(subset=["name"], keep="first", inplace=True)
    removed = initial_count - len(df)
    if removed > 0:
        logger.info(f"Removed {removed} duplicates.")

    # Convert back to Product objects
    df = df.replace({np.nan: None})
    records = cast(List[Dict[str, Any]], df.to_dict(orient="records"))
    cleaned_products = [Product(**record) for record in records]

    logger.info(f"Cleaning complete: {len(cleaned_products)} products ready.")
    return cleaned_products
