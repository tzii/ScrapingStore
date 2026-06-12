"""
Browser Product Scraper
=======================
Uses Playwright for dynamic scraping with true concurrency.
"""

import asyncio
import re
from typing import Any, List, Optional
from playwright.async_api import (
    async_playwright,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)

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
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self._scrape_async(max_pages)).result()
        return asyncio.run(self._scrape_async(max_pages))

    @staticmethod
    def _extract_price(text: str) -> float:
        """Extract price from card text using regex."""
        match = re.search(r"(\d+(?:[.,]\d{2})?)\s*€", text)
        if match:
            return float(match.group(1).replace(",", "."))
        return 0.0

    @staticmethod
    def _extract_availability(text: str) -> str:
        """Extract availability status from card text."""
        lower = text.lower()
        if "in stock" in lower or "add to basket" in lower:
            return "In Stock"
        if "out of stock" in lower or "unavailable" in lower:
            return "Out of Stock"
        return "Unknown"

    async def _scrape_async(self, max_pages: Optional[int]) -> List[Product]:
        logger.info(f"Starting browser scrape of {self.base_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT_FALLBACK)
            all_products = []
            page_num = 1
            consecutive_empty = 0
            semaphore = asyncio.Semaphore(3)

            try:
                while not max_pages or page_num <= max_pages:
                    urls = self._batch_urls(page_num, max_pages)
                    if not urls:
                        break

                    tasks = [
                        self._scrape_single_page(context, url, semaphore)
                        for url in urls
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    batch_products = self._collect_results(results)
                    all_products.extend(batch_products)

                    if batch_products:
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= 2:
                            logger.info("Stopping: consecutive empty batches.")
                            break

                    page_num += len(urls)
                    if self.delay > 0:
                        await asyncio.sleep(self.delay)
            finally:
                await browser.close()

            logger.info(f"Browser scrape complete. Total products: {len(all_products)}")
            return all_products

    def _batch_urls(
        self, page_num: int, max_pages: Optional[int], batch_size: int = 3
    ) -> List[str]:
        """Build the next bounded batch of paginated URLs."""
        urls = []
        for offset in range(batch_size):
            current_page = page_num + offset
            if max_pages and current_page > max_pages:
                break
            url = (
                f"{self.base_url}?page={current_page}"
                if current_page > 1
                else self.base_url
            )
            urls.append(url)
        return urls

    @staticmethod
    def _collect_results(results: List[Any]) -> List[Product]:
        """Collect successful page results and log page-level failures."""
        products = []
        for result in results:
            if isinstance(result, list):
                products.extend(result)
            else:
                logger.error(f"Page error: {result}")
        return products

    async def _scrape_single_page(
        self, context: BrowserContext, url: str, semaphore: asyncio.Semaphore
    ) -> List[Product]:
        async with semaphore:
            page = await context.new_page()
            products = []
            try:
                logger.info(f"Scraping {url}...")
                await page.goto(
                    url, timeout=DEFAULT_TIMEOUT * 1000, wait_until="domcontentloaded"
                )

                # Wait for content to render
                try:
                    await page.wait_for_selector("div.product-card", timeout=5000)
                except PlaywrightTimeoutError:
                    # If timeout, we proceed to count (which will be 0)
                    pass

                # Use Playwright Locators instead of JS injection
                # Tightened selector: removed generic 'css-' class match
                cards = page.locator("div.product-card")
                count = await cards.count()

                if count == 0:
                    logger.warning(f"No products on {url}")
                    return []

                for i in range(count):
                    card = cards.nth(i)
                    try:
                        name_el = card.locator("h4")
                        if await name_el.count() == 0:
                            continue

                        name = await name_el.inner_text()
                        text = await card.inner_text()

                        price = self._extract_price(text)
                        availability = self._extract_availability(text)

                        img_el = card.locator("img")
                        img_src = (
                            await img_el.get_attribute("src")
                            if await img_el.count() > 0
                            else None
                        )

                        products.append(
                            Product(
                                name=name,
                                source_url=url,
                                price=price,
                                availability=availability,
                                image_url=img_src,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Skipping unparsable card on {url}: {e}")
                        continue

            except Exception as e:
                logger.exception(f"Failed to scrape {url}: {e}")
                raise
            finally:
                await page.close()

            return products
