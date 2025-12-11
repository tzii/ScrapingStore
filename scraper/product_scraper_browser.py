"""
Playwright-based Product Scraper
=================================
Scraper for JavaScript-rendered sites like Oxylabs sandbox.

This uses Playwright to render JavaScript and extract prices that
are not available in the static HTML.
"""

import asyncio
import logging
from typing import Optional

import pandas as pd
from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)


async def scrape_page_with_browser(page: Page, url: str) -> list[dict]:
    """
    Scrape a single page using Playwright browser.
    
    Args:
        page: Playwright Page object
        url: URL to scrape
        
    Returns:
        List of product dictionaries
    """
    logger.info(f"Scraping (browser): {url}")
    
    await page.goto(url, wait_until='networkidle', timeout=30000)
    
    # Wait for product cards to load
    await page.wait_for_selector('a.card-header', timeout=10000)
    
    products = []
    
    # Use JavaScript to extract product data directly from the DOM
    # This is more reliable than Playwright element queries for complex text
    products_data = await page.evaluate('''() => {
        const products = [];
        const cards = document.querySelectorAll('a.card-header');
        
        cards.forEach(card => {
            const h4 = card.querySelector('h4');
            const name = h4 ? h4.textContent.trim() : null;
            
            if (!name || name === 'Video Games to scrape') return;
            
            // Get the parent container that might have the price
            let container = card.parentElement;
            for (let i = 0; i < 5; i++) {
                if (container && container.textContent && container.textContent.includes('€')) {
                    break;
                }
                if (container.parentElement) {
                    container = container.parentElement;
                }
            }
            
            // Get full text from the container
            const fullText = container ? container.textContent : card.textContent;
            
            // Extract price - look for XX,XX € pattern
            const priceMatch = fullText.match(/(\\d{1,3}[,\\.]\\d{2})\\s*€/);
            const price = priceMatch ? priceMatch[0] : null;
            
            // Extract availability
            let availability = 'Unknown';
            if (fullText.includes('Out of Stock')) {
                availability = 'Out of Stock';
            } else if (fullText.includes('In stock') || fullText.includes('Add to Basket')) {
                availability = 'In Stock';
            }
            
            // Get image
            const img = card.querySelector('img');
            const imageUrl = img ? (img.getAttribute('src') || null) : null;
            
            products.push({
                name: name,
                price: price,
                availability: availability,
                image_url: imageUrl
            });
        });
        
        return products;
    }''')
    
    products = products_data if products_data else []
    logger.info(f"Extracted {len(products)} products from {url}")
    return products


async def scrape_all_pages_async(
    base_url: str = "https://sandbox.oxylabs.io/products",
    max_pages: Optional[int] = None,
    delay_seconds: float = 1.0
) -> list[dict]:
    """
    Scrape all pages asynchronously using Playwright.
    
    Args:
        base_url: Base URL of products listing
        max_pages: Maximum pages to scrape (None for all)
        delay_seconds: Delay between pages
        
    Returns:
        List of all products
    """
    logger.info(f"Starting browser-based scrape of {base_url}")
    logger.info(f"Max pages: {max_pages}, Delay: {delay_seconds}s")
    
    all_products = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        page_num = 1
        consecutive_empty = 0
        max_consecutive_empty = 3
        
        while True:
            if max_pages and page_num > max_pages:
                logger.info(f"Reached max pages limit ({max_pages})")
                break
            
            url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
            
            try:
                products = await scrape_page_with_browser(page, url)
                
                if not products:
                    consecutive_empty += 1
                    logger.warning(f"No products found on page {page_num}")
                    if consecutive_empty >= max_consecutive_empty:
                        logger.info("Stopping: multiple consecutive empty pages")
                        break
                else:
                    consecutive_empty = 0
                    all_products.extend(products)
                    logger.info(f"Total products so far: {len(all_products)}")
                
                page_num += 1
                
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                    
            except Exception as e:
                logger.error(f"Error on page {page_num}: {e}")
                consecutive_empty += 1
                page_num += 1
                if consecutive_empty >= max_consecutive_empty:
                    break
        
        await browser.close()
    
    logger.info(f"Browser scraping complete. Total products: {len(all_products)}")
    return all_products


def scrape_products_browser(
    base_url: str = "https://sandbox.oxylabs.io/products",
    max_pages: Optional[int] = None,
    delay_seconds: float = 0.5,
    save_raw: bool = True,
    output_path: str = "data/products_raw.csv"
) -> pd.DataFrame:
    """
    Main entry point - scrape products using Playwright browser.
    
    Args:
        base_url: Base URL for products
        max_pages: Max pages to scrape (None for all ~94 pages)
        delay_seconds: Delay between page requests
        save_raw: Whether to save raw CSV
        output_path: Path for raw CSV output
        
    Returns:
        DataFrame with scraped products
    """
    # Run async scraper
    all_products = asyncio.run(
        scrape_all_pages_async(base_url, max_pages, delay_seconds)
    )
    
    # Create DataFrame
    df = pd.DataFrame(all_products)
    
    if not df.empty:
        df['scraped_at'] = pd.Timestamp.now()
        df['source_url'] = base_url
    
    # Save if requested
    if save_raw and not df.empty:
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Raw data saved to {output_path}")
    
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test scrape 2 pages
    df = scrape_products_browser(max_pages=2)
    print(f"\nScraped {len(df)} products")
    if not df.empty:
        print("\nSample:")
        print(df.head())
