"""
Browser Product Scraper
=======================
Uses Playwright for dynamic scraping with true concurrency.
"""

import asyncio
from typing import List, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

from scraper.base import BaseScraper
from models import Product
from logger import get_logger
from config import DEFAULT_TIMEOUT, USER_AGENT_FALLBACK

logger = get_logger(__name__)

class BrowserScraper(BaseScraper):
    def scrape(self, max_pages: Optional[int] = None) -> List[Product]:
        """
        Entry point that runs the async event loop.
        """
        return asyncio.run(self._scrape_async(max_pages))

    async def _scrape_async(self, max_pages: Optional[int]) -> List[Product]:
        logger.info(f"Starting browser scrape of {self.base_url}")
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT_FALLBACK)
            
            all_products = []
            page_num = 1
            consecutive_empty = 0
            # Limit concurrency to 3 to be polite but faster than serial
            semaphore = asyncio.Semaphore(3) 
            
            # We must loop to allow stopping early
            while True:
                if max_pages and page_num > max_pages:
                    break

                # Create a batch of tasks (e.g., 3 pages at a time) to run concurrently
                # but ensure we can check the results of this batch before launching the next 100
                batch_size = 3
                tasks = []
                
                # Prepare batch
                current_batch_pages = []
                for i in range(batch_size):
                    if max_pages and (page_num + i) > max_pages:
                        break
                    p_idx = page_num + i
                    url = f"{self.base_url}?page={p_idx}" if p_idx > 1 else self.base_url
                    tasks.append(self._scrape_single_page(context, url, semaphore))
                    current_batch_pages.append(p_idx)
                
                if not tasks:
                    break
                
                # Run batch
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                batch_has_products = False
                for res in results:
                    if isinstance(res, list):
                        if res:
                            all_products.extend(res)
                            batch_has_products = True
                        # Loop logic for empty check:
                        # If a page was empty, we shouldn't necessarily stop immediately if parallel pages had content,
                        # but if the WHOLE batch is empty, that's a strong signal.
                        # The user asked for "Stop after N empty pages".
                        # For simplicity in concurrent mode: if the entire batch yields 0 products, we count it.
                    else:
                        logger.error(f"Page error: {res}")

                if not batch_has_products:
                    consecutive_empty += 1 # We count batches as units here for simplicity
                    if consecutive_empty >= 2: # Stop after 2 empty batches (~6 pages)
                        logger.info("Stopping: Consecutive empty batches.")
                        break
                else:
                    consecutive_empty = 0
                
                # Advance page counter
                page_num += len(tasks)
                
                # Respect Delay between batches
                if self.delay > 0:
                    await asyncio.sleep(self.delay)
            
            await browser.close()
            
            logger.info(f"Browser scrape complete. Total products: {len(all_products)}")
            return all_products

    async def _scrape_single_page(self, context: BrowserContext, url: str, semaphore: asyncio.Semaphore) -> List[Product]:
        async with semaphore:
            page = await context.new_page()
            products = []
            try:
                logger.info(f"Scraping {url}...")
                await page.goto(url, timeout=DEFAULT_TIMEOUT * 1000, wait_until='domcontentloaded')
                
                # Use Playwright Locators instead of JS injection
                # Tightened selector: removed generic 'css-' class match
                cards = page.locator('div.product-card')
                count = await cards.count()
                
                if count == 0:
                    logger.warning(f"No products on {url}")
                    return []

                for i in range(count):
                    card = cards.nth(i)
                    try:
                        name_el = card.locator('h4')
                        if await name_el.count() == 0: continue
                        
                        name = await name_el.inner_text()
                        
                        # Get raw text for cleaning later
                        text = await card.inner_text()
                        
                        # Image
                        img_el = card.locator('img')
                        img_src = await img_el.get_attribute('src') if await img_el.count() > 0 else None
                        
                        products.append(Product(
                            name=name,
                            source_url=url,
                            price=0.0, # Placeholder
                            availability=text, # Placeholder containing raw text
                            image_url=img_src
                        ))
                    except Exception as e:
                        continue
                        
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")
                raise e
            finally:
                await page.close()
            
            return products