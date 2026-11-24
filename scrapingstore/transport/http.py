"""HTTP transport with per-host spacing, ETag support, timing, and raw HTML capture."""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests
from bs4 import Tag

from scrapingstore.config import get_settings
from scrapingstore.ledger.models import Product
from scrapingstore.logger import get_logger
from scrapingstore.sources.oxylabs import extract_price, parse_card
from scrapingstore.sources.results import PageResult, ScrapeRunResult
from scrapingstore.transport.collector import BaseScraper
from scrapingstore.transport.rate_limit import TRANSIENT_STATUSES, retry_delay

logger = get_logger(__name__)


class StaticScraper(BaseScraper):
    """Requests-based static HTML collector."""

    def __init__(self, base_url: Optional[str] = None, delay: float = 1.0, **kwargs):
        super().__init__(base_url, delay, **kwargs)
        self.session = self._create_session()
        self._etags: Dict[str, str] = {}

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": get_settings().user_agent})
        return session

    def close(self) -> None:
        self.session.close()

    def scrape(self, max_pages: Optional[int] = None) -> ScrapeRunResult:
        run = self.new_run(max_pages, "static")
        deadline = time.monotonic() + self.run_timeout
        seen: set[str] = set()
        limit = min(max_pages or self.page_budget, self.page_budget)
        try:
            for number in range(1, limit + 1):
                if not self.remaining(deadline):
                    return run.finish("deadline")
                try:
                    page = self._get_page(number, deadline)
                except KeyboardInterrupt:
                    run.pages.append(
                        PageResult(
                            number,
                            self.page_url(number),
                            errors=["cancelled during request"],
                        )
                    )
                    raise
                run.pages.append(page)
                if self.on_page is not None:
                    self.on_page(page, run)
                if not self.remaining(deadline):
                    return run.finish("deadline", allow_source_end=False)
                reason = self.stopping_reason(run, seen, page)
                if reason:
                    return run.finish(reason)
                if number < limit and self.delay > 0:
                    time.sleep(min(self.delay, self.remaining(deadline)))
        except KeyboardInterrupt:
            run.finish("cancelled")
            raise
        return run.finish(
            "page_limit"
            if max_pages and max_pages <= self.page_budget
            else "page_budget"
        )

    def _get_page(self, number: int, deadline: float) -> PageResult:
        url = self.page_url(number)
        result = PageResult(number, url)
        for attempt in range(1, self.max_attempts + 1):
            result.attempts = attempt
            if not self.remaining(deadline):
                result.errors = ["run deadline exceeded"]
                return result
            retry_after = None
            started = time.perf_counter()
            try:
                timeout_val = min(self.timeout, self.remaining(deadline))
                if url in self._etags:
                    response = self.session.get(
                        url,
                        timeout=timeout_val,
                        headers={"If-None-Match": self._etags[url]},
                    )
                else:
                    response = self.session.get(url, timeout=timeout_val)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                result.http_status = response.status_code
                result.elapsed_ms = round(elapsed_ms, 2)
                if 200 <= response.status_code < 300:
                    etag = (
                        response.headers.get("ETag")
                        if isinstance(getattr(response, "headers", None), dict)
                        or hasattr(getattr(response, "headers", None), "get")
                        else None
                    )
                    if etag:
                        self._etags[url] = etag
                    parsed = self.adapter.parse_page(response.content, url, number)
                    parsed.attempts = attempt
                    parsed.http_status = response.status_code
                    parsed.elapsed_ms = result.elapsed_ms
                    parsed.bytes_received = len(response.content)
                    return parsed
                result.errors = [f"HTTP {response.status_code}"]
                if response.status_code not in TRANSIENT_STATUSES:
                    return result
                retry_after = (
                    response.headers.get("Retry-After")
                    if hasattr(getattr(response, "headers", None), "get")
                    else None
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                result.elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
                result.errors = [f"{type(exc).__name__}: {exc}"]
            except Exception as exc:
                result.elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
                result.errors = [f"{type(exc).__name__}: {exc}"]
                return result
            if attempt < self.max_attempts:
                pause = retry_delay(attempt, retry_after)
                if pause >= self.remaining(deadline):
                    result.errors.append("retry exceeds remaining run deadline")
                    return result
                time.sleep(pause)
        return result

    def _parse_page(self, content: bytes, url: str) -> List[Product]:
        """Compatibility helper for parsing fixtures; collection uses PageResult."""
        return self.adapter.parse_page(content, url, 1).products

    @staticmethod
    def _extract_price(card: Tag) -> Optional[float]:
        return extract_price(card).value

    @staticmethod
    def _extract_availability(card: Tag) -> str:
        return parse_card(card, "https://fixture.test").availability
