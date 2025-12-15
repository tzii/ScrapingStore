"""
Base Scraper
============
Abstract base class for product scrapers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import time
from models import Product
from logger import get_logger
from config import BASE_URL

logger = get_logger(__name__)

class BaseScraper(ABC):
    def __init__(self, base_url: str = BASE_URL, delay: float = 1.0):
        self.base_url = base_url
        self.delay = delay

    @abstractmethod
    def scrape(self, max_pages: Optional[int] = None) -> List[Product]:
        """
        Main entry point for scraping.
        """
        pass