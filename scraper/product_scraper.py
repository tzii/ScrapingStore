"""Requests acquisition with explicit page outcomes and bounded retries."""

import time
from typing import List, Optional

import requests
from bs4 import Tag

from config import USER_AGENT_FALLBACK
from models import Product
from scraper.base import BaseScraper, TRANSIENT_STATUSES, retry_delay
from scraper.parsing import extract_price, parse_card, parse_page
from scraper.results import PageResult, ScrapeRunResult


class StaticScraper(BaseScraper):
    def __init__(self, base_url: str, delay: float = 1.0, **kwargs):
        super().__init__(base_url, delay, **kwargs)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT_FALLBACK})
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
                if not self.remaining(deadline):
                    # This page's end marker was also observed after the deadline.
                    return run.finish("deadline", allow_source_end=False)
                reason = self.stopping_reason(run, seen, page)
                if reason:
                    return run.finish(reason)
                if number < limit:
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
            try:
                response = self.session.get(
                    url, timeout=min(self.timeout, self.remaining(deadline))
                )
                result.http_status = response.status_code
                if 200 <= response.status_code < 300:
                    parsed = parse_page(response.content, url, number)
                    parsed.attempts = attempt
                    parsed.http_status = response.status_code
                    return parsed
                result.errors = [f"HTTP {response.status_code}"]
                if response.status_code not in TRANSIENT_STATUSES:
                    return result
                retry_after = response.headers.get("Retry-After")
            except (requests.Timeout, requests.ConnectionError) as exc:
                result.errors = [f"{type(exc).__name__}: {exc}"]
            except Exception as exc:
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
        return parse_page(content, url, 1).products

    @staticmethod
    def _extract_price(card: Tag) -> Optional[float]:
        return extract_price(card).value

    @staticmethod
    def _extract_availability(card: Tag) -> str:
        return parse_card(card, "https://fixture.test").availability
