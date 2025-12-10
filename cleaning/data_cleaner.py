"""
Data Cleaner Module
===================
Pandas-based data cleaning for scraped product data.

This module handles:
- Currency symbol removal and price conversion
- Data type standardization
- Missing value handling
- Duplicate removal
- Data validation

Author: Portfolio Project
Date: 2024
"""

import logging
import re
from typing import Optional

import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Price Cleaning Functions
# =============================================================================

def clean_price(price_str: Optional[str]) -> Optional[float]:
    """
    Convert European price format to float.
    
    Handles formats like:
    - "88,99 €" -> 88.99
    - "88.99 €" -> 88.99
    - "88,99€"  -> 88.99
    - "88.99"   -> 88.99
    
    Args:
        price_str: Price string with potential currency symbols
    
    Returns:
        Float price value or None if conversion fails
    
    Example:
        >>> clean_price("88,99 €")
        88.99
        >>> clean_price(None)
        None
    """
    if pd.isna(price_str) or price_str is None:
        return None
    
    try:
        # Convert to string if not already
        price_str = str(price_str)
        
        # Remove currency symbols and whitespace
        cleaned = price_str.replace('€', '').replace('$', '').replace('£', '').strip()
        
        # Handle European format (comma as decimal separator)
        # First, check if it looks like European format
        if ',' in cleaned and '.' not in cleaned:
            # European format: replace comma with period
            cleaned = cleaned.replace(',', '.')
        elif ',' in cleaned and '.' in cleaned:
            # Mixed format: remove thousands separator (could be either)
            # Assume last separator is decimal
            if cleaned.rfind(',') > cleaned.rfind('.'):
                # Comma is decimal separator
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                # Period is decimal separator
                cleaned = cleaned.replace(',', '')
        
        return float(cleaned)
    except (ValueError, AttributeError) as e:
        logger.debug(f"Could not convert price '{price_str}': {e}")
        return None


def clean_price_column(df: pd.DataFrame, column: str = 'price') -> pd.DataFrame:
    """
    Clean entire price column in a DataFrame.
    
    Creates two new columns:
    - price_original: Preserves the original price string
    - price: Contains the cleaned float value
    
    Args:
        df: DataFrame with price column
        column: Name of the price column
    
    Returns:
        DataFrame with cleaned price column
    """
    df = df.copy()
    
    if column not in df.columns:
        logger.warning(f"Column '{column}' not found in DataFrame")
        return df
    
    # Preserve original
    df['price_original'] = df[column]
    
    # Apply cleaning function
    df[column] = df[column].apply(clean_price)
    
    # Log statistics
    null_count = df[column].isna().sum()
    valid_count = df[column].notna().sum()
    logger.info(f"Price cleaning: {valid_count} valid, {null_count} null values")
    
    return df


# =============================================================================
# Availability Standardization
# =============================================================================

def standardize_availability(availability: Optional[str]) -> str:
    """
    Standardize availability status to consistent values.
    
    Args:
        availability: Raw availability string
    
    Returns:
        Standardized string: "In Stock", "Out of Stock", or "Unknown"
    """
    if pd.isna(availability) or availability is None:
        return "Unknown"
    
    availability_lower = str(availability).lower().strip()
    
    if 'in stock' in availability_lower or availability_lower == 'available':
        return "In Stock"
    elif 'out of stock' in availability_lower or 'unavailable' in availability_lower:
        return "Out of Stock"
    else:
        return "Unknown"


def clean_availability_column(df: pd.DataFrame, column: str = 'availability') -> pd.DataFrame:
    """
    Clean and standardize availability column.
    
    Args:
        df: DataFrame with availability column
        column: Name of the availability column
    
    Returns:
        DataFrame with standardized availability
    """
    df = df.copy()
    
    if column not in df.columns:
        logger.warning(f"Column '{column}' not found in DataFrame")
        return df
    
    df[column] = df[column].apply(standardize_availability)
    
    # Convert to categorical for efficiency
    df[column] = pd.Categorical(
        df[column],
        categories=["In Stock", "Out of Stock", "Unknown"],
        ordered=False
    )
    
    # Log distribution
    distribution = df[column].value_counts()
    logger.info(f"Availability distribution:\n{distribution}")
    
    return df


# =============================================================================
# Missing Value Handling
# =============================================================================

def handle_missing_values(
    df: pd.DataFrame,
    strategy: str = 'flag',
    price_fill: Optional[float] = None
) -> pd.DataFrame:
    """
    Handle missing values in the DataFrame.
    
    Args:
        df: DataFrame to process
        strategy: Handling strategy
            - 'flag': Add boolean columns indicating missing values
            - 'drop': Remove rows with any missing values
            - 'fill': Fill missing values with defaults
        price_fill: Value to use for filling missing prices (only if strategy='fill')
    
    Returns:
        DataFrame with handled missing values
    """
    df = df.copy()
    
    # Log initial missing values
    missing_before = df.isna().sum()
    logger.info(f"Missing values before handling:\n{missing_before[missing_before > 0]}")
    
    if strategy == 'flag':
        # Add flag columns for missing values
        for col in ['name', 'price', 'availability', 'image_url']:
            if col in df.columns:
                df[f'{col}_missing'] = df[col].isna()
        
    elif strategy == 'drop':
        # Drop rows with missing essential data
        essential_cols = ['name', 'price']
        existing_essential = [col for col in essential_cols if col in df.columns]
        df = df.dropna(subset=existing_essential)
        logger.info(f"Dropped {len(df) - len(df)} rows with missing essential data")
        
    elif strategy == 'fill':
        # Fill missing values
        if 'price' in df.columns and price_fill is not None:
            df['price'] = df['price'].fillna(price_fill)
        if 'availability' in df.columns:
            df['availability'] = df['availability'].fillna("Unknown")
        if 'image_url' in df.columns:
            df['image_url'] = df['image_url'].fillna("")
    
    # Log final missing values
    missing_after = df.isna().sum()
    logger.info(f"Missing values after handling:\n{missing_after[missing_after > 0]}")
    
    return df


# =============================================================================
# Duplicate Removal
# =============================================================================

def remove_duplicates(
    df: pd.DataFrame,
    subset: Optional[list] = None,
    keep: str = 'first'
) -> pd.DataFrame:
    """
    Remove duplicate rows from DataFrame.
    
    Args:
        df: DataFrame to deduplicate
        subset: Columns to consider for identifying duplicates
                (default: ['name'] for product deduplication)
        keep: Which duplicate to keep ('first', 'last', or False for none)
    
    Returns:
        DataFrame with duplicates removed
    """
    df = df.copy()
    
    if subset is None:
        subset = ['name'] if 'name' in df.columns else None
    
    initial_count = len(df)
    df = df.drop_duplicates(subset=subset, keep=keep)
    removed_count = initial_count - len(df)
    
    logger.info(f"Removed {removed_count} duplicate rows (kept {len(df)})")
    
    return df


# =============================================================================
# Text Cleaning
# =============================================================================

def clean_text_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    Clean text in a specified column.
    
    Performs:
    - Stripping whitespace
    - Removing extra spaces
    - Handling encoding issues
    
    Args:
        df: DataFrame to process
        column: Column name to clean
    
    Returns:
        DataFrame with cleaned text column
    """
    df = df.copy()
    
    if column not in df.columns:
        return df
    
    # Strip whitespace and normalize spaces
    df[column] = df[column].astype(str).str.strip()
    df[column] = df[column].str.replace(r'\s+', ' ', regex=True)
    
    # Replace 'nan' strings with actual NaN
    df[column] = df[column].replace('nan', np.nan)
    df[column] = df[column].replace('None', np.nan)
    
    return df


# =============================================================================
# Main Cleaning Pipeline
# =============================================================================

def clean_product_data(
    df: pd.DataFrame,
    save_cleaned: bool = True,
    output_path: str = "data/products_cleaned.csv"
) -> pd.DataFrame:
    """
    Complete data cleaning pipeline for scraped product data.
    
    This function orchestrates all cleaning steps:
    1. Clean text columns (names)
    2. Clean and convert prices
    3. Standardize availability
    4. Handle missing values
    5. Remove duplicates
    6. Add derived columns
    
    Args:
        df: Raw DataFrame from scraper
        save_cleaned: Whether to save cleaned data
        output_path: Path for saving cleaned CSV
    
    Returns:
        Cleaned DataFrame ready for analysis
    
    Example:
        >>> raw_df = pd.read_csv("data/products_raw.csv")
        >>> cleaned_df = clean_product_data(raw_df)
    """
    logger.info(f"Starting data cleaning pipeline. Input rows: {len(df)}")
    
    if df.empty:
        logger.warning("Empty DataFrame provided")
        return df
    
    # Step 1: Clean text columns
    logger.info("Step 1: Cleaning text columns")
    if 'name' in df.columns:
        df = clean_text_column(df, 'name')
    
    # Step 2: Clean prices
    logger.info("Step 2: Cleaning price column")
    df = clean_price_column(df)
    
    # Step 3: Standardize availability
    logger.info("Step 3: Standardizing availability")
    df = clean_availability_column(df)
    
    # Step 4: Handle missing values (using flag strategy)
    logger.info("Step 4: Handling missing values")
    df = handle_missing_values(df, strategy='flag')
    
    # Step 5: Remove duplicates
    logger.info("Step 5: Removing duplicates")
    df = remove_duplicates(df)
    
    # Step 6: Add derived columns
    logger.info("Step 6: Adding derived columns")
    if 'price' in df.columns:
        # Create price categories
        df['price_category'] = pd.cut(
            df['price'],
            bins=[0, 20, 50, 100, float('inf')],
            labels=['Budget', 'Mid-Range', 'Premium', 'Luxury'],
            include_lowest=True
        )
    
    # Final statistics
    logger.info(f"Cleaning complete. Output rows: {len(df)}")
    logger.info(f"Columns: {list(df.columns)}")
    
    # Save cleaned data
    if save_cleaned:
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Cleaned data saved to {output_path}")
    
    return df


# =============================================================================
# Module Entry Point
# =============================================================================

if __name__ == "__main__":
    # Example usage
    print("Data Cleaner Module")
    print("=" * 50)
    
    # Test with sample data
    sample_data = pd.DataFrame({
        'name': ['  Product A  ', 'Product B', 'Product A', 'Product C'],
        'price': ['88,99 €', '45.50 €', '88,99 €', None],
        'availability': ['In stock', 'out of stock', 'In stock', 'available'],
        'image_url': ['http://example.com/a.jpg', None, 'http://example.com/a.jpg', 'http://example.com/c.jpg']
    })
    
    print("\nOriginal Data:")
    print(sample_data)
    
    cleaned = clean_product_data(sample_data, save_cleaned=False)
    
    print("\nCleaned Data:")
    print(cleaned)
    print("\nData Types:")
    print(cleaned.dtypes)
