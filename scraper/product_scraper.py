"""
Product Scraper Module
======================
Web scraper for extracting product data from Oxylabs sandbox e-commerce site.

This module implements robust web scraping with:
- Proper HTTP session management with retry logic
- User-Agent headers to simulate browser requests
- Rate limiting to respect server resources
- Comprehensive error handling and logging

Author: Portfolio Project
Date: 2024
"""

import time
import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# HTTP Session Configuration
# =============================================================================

def create_session(
    max_retries: int = 3,
    backoff_factor: float = 0.5,
    timeout: int = 30
) -> requests.Session:
    """
    Create a configured HTTP session with retry logic.
    
    Args:
        max_retries: Maximum number of retry attempts for failed requests
        backoff_factor: Factor for exponential backoff between retries
        timeout: Request timeout in seconds
    
    Returns:
        Configured requests.Session object
    
    Example:
        >>> session = create_session()
        >>> response = session.get("https://example.com")
    """
    session = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    # Mount adapter with retry strategy
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set realistic browser headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    return session


# =============================================================================
# Page Scraping Functions
# =============================================================================

def scrape_single_page(
    session: requests.Session,
    url: str,
    timeout: int = 30
) -> list[dict]:
    """
    Scrape products from a single page.
    
    Args:
        session: Configured requests session
        url: Full URL of the page to scrape
        timeout: Request timeout in seconds
    
    Returns:
        List of dictionaries containing product data
    
    Raises:
        requests.RequestException: If the HTTP request fails
    """
    logger.info(f"Scraping: {url}")
    
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        raise
    
    soup = BeautifulSoup(response.content, 'lxml')
    products = []
    
    # Find all product cards - they are contained in div elements with product info
    # The structure: each product has a card with image, title, price, and availability
    product_cards = soup.select('div.product-card')
    
    # If no product-card class, try alternative selectors based on the page structure
    if not product_cards:
        # Look for the main content area with products
        # Products are in a grid, each containing an anchor with h4 for title
        product_cards = soup.find_all('div', class_=lambda x: x and 'css-' in x)
        
    # Parse each product card
    for card in product_cards:
        product = extract_product_data(card)
        if product and product.get('name'):  # Only add if we got valid data
            products.append(product)
    
    # Alternative parsing strategy if above didn't work
    if not products:
        products = parse_products_alternative(soup)
    
    logger.info(f"Extracted {len(products)} products from page")
    return products


def extract_product_data(card) -> Optional[dict]:
    """
    Extract product data from a single product card element.
    
    Args:
        card: BeautifulSoup element representing a product card
    
    Returns:
        Dictionary with product data or None if extraction failed
    """
    try:
        # Try to find product name in h4 tag
        name_elem = card.find('h4')
        name = name_elem.get_text(strip=True) if name_elem else None
        
        if not name:
            return None
        
        # Find image URL
        img = card.find('img')
        image_url = None
        if img:
            image_url = img.get('src') or img.get('srcset', '').split()[0] if img.get('srcset') else None
        
        # Get all text content to find price and availability
        text_content = card.get_text(separator='|', strip=True)
        
        # Extract price (format: XX,XX € or XX.XX €)
        price = extract_price(text_content)
        
        # Extract availability
        availability = extract_availability(text_content)
        
        return {
            'name': name,
            'price': price,
            'availability': availability,
            'image_url': image_url
        }
    except Exception as e:
        logger.debug(f"Error extracting product data: {e}")
        return None


def parse_products_alternative(soup: BeautifulSoup) -> list[dict]:
    """
    Alternative parsing strategy for the Oxylabs sandbox site.
    This method looks for specific patterns in the HTML structure.
    
    Args:
        soup: BeautifulSoup object of the page
    
    Returns:
        List of product dictionaries
    """
    products = []
    
    # Find all h4 elements which contain product names
    h4_elements = soup.find_all('h4')
    
    for h4 in h4_elements:
        name = h4.get_text(strip=True)
        if not name or name in ['Video Games to scrape', '']:
            continue
        
        # Navigate up to find the parent container
        parent = h4.find_parent('a') or h4.find_parent('div')
        if not parent:
            continue
        
        # Go up more to get the full product card container
        card_container = parent
        for _ in range(5):  # Look up to 5 levels
            if card_container.parent:
                card_container = card_container.parent
                text = card_container.get_text()
                if '€' in text and ('In stock' in text or 'Out of Stock' in text):
                    break
        
        # Extract image
        img = parent.find('img') if parent else None
        image_url = None
        if img:
            image_url = img.get('src')
            if not image_url or 'data:' in image_url:
                srcset = img.get('srcset', '')
                if srcset:
                    image_url = srcset.split()[0] if srcset else None
        
        # Get text from the card container
        text_content = card_container.get_text(separator='|', strip=True) if card_container else ''
        
        # Extract price and availability
        price = extract_price(text_content)
        availability = extract_availability(text_content)
        
        products.append({
            'name': name,
            'price': price,
            'availability': availability,
            'image_url': image_url
        })
    
    return products


def extract_price(text: str) -> Optional[str]:
    """
    Extract price from text content.
    
    Args:
        text: Text containing price information
    
    Returns:
        Price string (e.g., "88,99 €") or None
    """
    import re
    
    # Match European price format: XX,XX € or XX.XX €, allowing for loose whitespace
    # matches: "88,99 €", "88.99€", "88 , 99 €"
    price_pattern = r'(\d{1,3}(?:[.,]\d{2})?)\s*€'
    match = re.search(price_pattern, text)
    
    if match:
        return f"{match.group(1)} €"
    return None


def extract_availability(text: str) -> str:
    """
    Extract availability status from text content.
    
    Args:
        text: Text containing availability information
    
    Returns:
        "In Stock", "Out of Stock", or "Unknown"
    """
    text_lower = text.lower()
    
    # "Add to Basket" button implies the item is purchasable (In Stock)
    if 'add to basket' in text_lower:
        return 'In Stock'
    elif 'in stock' in text_lower:
        return 'In Stock'
    elif 'out of stock' in text_lower or 'unavailable' in text_lower:
        return 'Out of Stock'
    else:
        return 'Unknown'


# =============================================================================
# Main Scraping Function
# =============================================================================

def scrape_products(
    base_url: str = "https://sandbox.oxylabs.io/products",
    max_pages: Optional[int] = 10,
    delay_seconds: float = 1.0,
    save_raw: bool = True,
    output_path: str = "data/products_raw.csv"
) -> pd.DataFrame:
    """
    Scrape products from multiple pages of the Oxylabs sandbox site.
    
    This is the main entry point for the scraping module. It handles:
    - Session creation with proper headers
    - Pagination through all specified pages
    - Rate limiting between requests
    - Error handling and logging
    - Optional saving of raw data
    
    Args:
        base_url: Base URL of the products listing page
        max_pages: Maximum number of pages to scrape (None for all pages)
        delay_seconds: Delay between page requests (rate limiting)
        save_raw: Whether to save raw data to CSV
        output_path: Path for saving raw CSV data
    
    Returns:
        DataFrame containing all scraped products
    
    Example:
        >>> df = scrape_products(max_pages=5)
        >>> print(f"Scraped {len(df)} products")
    """
    logger.info(f"Starting scrape of {base_url}")
    logger.info(f"Max pages: {max_pages}, Delay: {delay_seconds}s")
    
    session = create_session()
    all_products = []
    page = 1
    consecutive_empty = 0
    max_consecutive_empty = 3  # Stop after 3 consecutive empty pages
    
    while True:
        # Check if we've reached max pages
        if max_pages and page > max_pages:
            logger.info(f"Reached max pages limit ({max_pages})")
            break
        
        # Construct page URL
        url = f"{base_url}?page={page}" if page > 1 else base_url
        
        try:
            products = scrape_single_page(session, url)
            
            if not products:
                consecutive_empty += 1
                logger.warning(f"No products found on page {page}")
                if consecutive_empty >= max_consecutive_empty:
                    logger.info("Stopping: multiple consecutive empty pages")
                    break
            else:
                consecutive_empty = 0
                all_products.extend(products)
                logger.info(f"Total products so far: {len(all_products)}")
            
            page += 1
            
            # Rate limiting
            if delay_seconds > 0:
                time.sleep(delay_seconds)
                
        except requests.RequestException as e:
            logger.error(f"Error on page {page}: {e}")
            # Continue to next page on error
            page += 1
            consecutive_empty += 1
            if consecutive_empty >= max_consecutive_empty:
                break
    
    # Create DataFrame
    df = pd.DataFrame(all_products)
    
    # Add metadata columns
    if not df.empty:
        df['scraped_at'] = pd.Timestamp.now()
        df['source_url'] = base_url
    
    logger.info(f"Scraping complete. Total products: {len(df)}")
    
    # Save raw data
    if save_raw and not df.empty:
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Raw data saved to {output_path}")
    
    return df


# =============================================================================
# Module Entry Point
# =============================================================================

if __name__ == "__main__":
    # Example usage - scrape 3 pages for testing
    df = scrape_products(max_pages=3)
    print(f"\nScraped {len(df)} products")
    if not df.empty:
        print("\nSample data:")
        print(df.head())
