"""Shared bounded collection policy and source pagination helpers."""

from abc import ABC, abstractmethod
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import time
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import BASE_URL, DEFAULT_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF
from scraper.results import PageResult, ScrapeRunResult

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


def retry_delay(attempt: int, header: Optional[str]) -> float:
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    return float(min(30.0, RETRY_BACKOFF * 2 ** (attempt - 1)))


class BaseScraper(ABC):
    def __init__(
        self,
        base_url: str = BASE_URL,
        delay: float = 1.0,
        *,
        page_budget: int = 200,
        run_timeout: float = 1800,
        max_attempts: int = MAX_RETRIES + 1,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        if (
            page_budget < 1
            or run_timeout <= 0
            or max_attempts < 1
            or timeout <= 0
            or delay < 0
        ):
            raise ValueError(
                "Collection limits must be positive; delay must be non-negative"
            )
        self.last_run: Optional[ScrapeRunResult] = None
        self.base_url = base_url
        self.delay = delay
        self.page_budget = page_budget
        self.run_timeout = run_timeout
        self.max_attempts = max_attempts
        self.timeout = timeout

    def page_url(self, number: int) -> str:
        parts = urlsplit(self.base_url)
        query = [(key, value) for key, value in parse_qsl(parts.query) if key != "page"]
        if number > 1:
            query.append(("page", str(number)))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), "")
        )

    def new_run(self, max_pages: Optional[int], kind: str) -> ScrapeRunResult:
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be positive")
        self.last_run = ScrapeRunResult(
            self.base_url,
            max_pages,
            kind,
            configuration={
                "page_budget": self.page_budget,
                "run_timeout": self.run_timeout,
                "max_attempts": self.max_attempts,
                "timeout": self.timeout,
                "delay": self.delay,
                "delay_policy": (
                    "between batches" if kind == "browser" else "between pages"
                ),
            },
        )

        return self.last_run

    def close(self) -> None:
        """Release resources owned by this scraper."""

    @abstractmethod
    def scrape(self, max_pages: Optional[int] = None) -> ScrapeRunResult:
        pass

    @staticmethod
    def stopping_reason(
        run: ScrapeRunResult, seen: set[str], result: PageResult
    ) -> Optional[str]:
        if result.fingerprint and result.fingerprint in seen:
            result.errors.append(
                "repeated_page: source repeated previously collected content"
            )
            return "repeated_page"
        if result.fingerprint:
            seen.add(result.fingerprint)
        if result.source_end:
            return "source_end"
        processed = [page for page in run.pages if page.number <= result.number]
        if len(processed) >= 3 and all(p.status == "failed" for p in processed[-3:]):
            return "failure_budget"
        return None

    @staticmethod
    def remaining(deadline: float) -> float:
        return max(0.0, deadline - time.monotonic())
