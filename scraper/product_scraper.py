"""
Static Product Scraper
======================
Uses Requests and BeautifulSoup to scrape static HTML.
"""

import time
from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from scraper.base import BaseScraper
from models import Product
from logger import get_logger
from config import MAX_RETRIES, RETRY_BACKOFF, DEFAULT_TIMEOUT, USER_AGENT_FALLBACK

logger = get_logger(__name__)

class StaticScraper(BaseScraper):
    def __init__(self, base_url: str, delay: float = 1.0):
        super().__init__(base_url, delay)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({'User-Agent': USER_AGENT_FALLBACK})
        return session

    def scrape(self, max_pages: Optional[int] = None) -> List[Product]:
        logger.info(f"Starting static scrape of {self.base_url}")
        all_products = []
        page = 1
        consecutive_empty = 0
        
        while True:
            if max_pages and page > max_pages:
                break
            
            url = f"{self.base_url}?page={page}" if page > 1 else self.base_url
            try:
                logger.info(f"Scraping page {page}...")
                response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
                response.raise_for_status()
                
                products = self._parse_page(response.content, url)
                
                if not products:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info("Stopping: 3 consecutive empty pages.")
                        break
                else:
                    consecutive_empty = 0
                    all_products.extend(products)
                
                page += 1
                time.sleep(self.delay)
                
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                    
        return all_products

    def _parse_page(self, content: bytes, url: str) -> List[Product]:
        soup = BeautifulSoup(content, 'html.parser')
        products = []
        
        cards = soup.select('div.product-card')
        # Fallback selector
        if not cards:
            cards = soup.find_all('div', class_=lambda x: x and 'css-' in x)

        for card in cards:
            try:
                name_elem = card.find('h4')
                if not name_elem: continue
                name = name_elem.get_text(strip=True)
                
                # Simple text extraction for price/availability
                text = card.get_text(separator='|', strip=True)
                
                # Create partial product - Cleaning will happen in pipeline
                p = Product(
                    name=name,
                    source_url=url,
                    # Store raw strings temporarily; cleaner fixes them
                    price=0.0, 
                    availability=text,
                    image_url=card.find('img')['src'] if card.find('img') else None
                )
                products.append(p)
            except Exception as e:
                logger.warning(f"Failed to parse product on {url}: {e}")
                continue
                
        return products