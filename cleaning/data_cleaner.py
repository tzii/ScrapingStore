"""
Data Cleaner Module
===================
Vectorized data cleaning pipeline using Pandas.
"""

from typing import List
import pandas as pd
import numpy as np
from models import Product
from logger import get_logger

logger = get_logger(__name__)


def clean_products(products: List[Product]) -> List[Product]:
    """
    Clean a list of Product objects using vectorized Pandas operations.
    """
    if not products:
        return []

    logger.info(f"Cleaning {len(products)} products...")

    # Convert to DataFrame
    df = pd.DataFrame([p.model_dump() for p in products])

    # 1. Clean Price
    # Extract price using regex from 'availability' column if 'price' is 0
    # (Since scrapers put raw text in 'availability' temporarily)
    # Pattern: XX,XX € or XX.XX €

    # 1. Clean Price
    # Extract price only if it's missing or zero
    if "availability" in df.columns:
        # Create a mask for rows where price is 0 or NaN
        if "price" not in df.columns:
            df["price"] = 0.0

        mask_price_invalid = pd.to_numeric(df["price"], errors="coerce").fillna(0) <= 0

        if mask_price_invalid.any():
            price_pattern = r"(\d{1,3}(?:[.,]\d{2})?)\s*€"
            extracted_price = df.loc[mask_price_invalid, "availability"].str.extract(
                price_pattern
            )[0]

            # Normalize decimal separator
            extracted_price = extracted_price.str.replace(",", ".", regex=False)

            # Update only invalid prices
            df.loc[mask_price_invalid, "price"] = pd.to_numeric(
                extracted_price, errors="coerce"
            ).fillna(0.0)
    elif "price" not in df.columns:
        df["price"] = 0.0

    # 2. Clean Availability
    # "In Stock", "Out of Stock", "Unknown"
    # Case insensitive search
    df["availability_clean"] = "Unknown"

    text_col = df["availability"].str.lower()
    df.loc[
        text_col.str.contains("in stock|add to basket", na=False), "availability_clean"
    ] = "In Stock"
    df.loc[
        text_col.str.contains("out of stock|unavailable", na=False),
        "availability_clean",
    ] = "Out of Stock"

    df["availability"] = df["availability_clean"]
    df.drop(columns=["availability_clean"], inplace=True)

    # 3. Clean Name
    df["name"] = df["name"].str.strip()

    # 4. Deduplicate (by name)
    initial_count = len(df)
    df.drop_duplicates(subset=["name"], keep="first", inplace=True)
    logger.info(f"Removed {initial_count - len(df)} duplicates.")

    # Convert back to Product objects
    # Handle NaN values (which break SQLModel validation for Optionals if passed as float('nan'))
    df = df.replace({np.nan: None})

    # Vectorized List Comprehension is already fast enough for this scale vs strict dict mapping
    cleaned_products = [Product(**record) for record in df.to_dict(orient="records")]

    return cleaned_products
