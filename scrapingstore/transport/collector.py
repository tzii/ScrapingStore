"""Shared BaseScraper policy and --type auto smart transport collector."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Callable, Optional

from scrapingstore.config import get_settings
from scrapingstore.sources.base import SourceAdapter, default_page_url
from scrapingstore.sources.oxylabs import OxylabsAdapter
from scrapingstore.sources.results import PageResult, ScrapeRunResult

ProgressCallback = Callable[[PageResult, ScrapeRunResult], None]


class BaseScraper(ABC):
    """Shared bounded collection policy, pagination, and stop-reason evaluation."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        delay: float = 1.0,
        *,
        adapter: Optional[SourceAdapter] = None,
        page_budget: int = 200,
        run_timeout: float = 1800,
        max_attempts: Optional[int] = None,
        timeout: Optional[float] = None,
        on_page: Optional[ProgressCallback] = None,
    ):
        settings = get_settings()
        max_att = settings.max_retries + 1 if max_attempts is None else max_attempts
        req_timeout = float(settings.default_timeout) if timeout is None else float(timeout)
        if (
            page_budget < 1
            or run_timeout <= 0
            or max_att < 1
            or req_timeout <= 0
            or delay < 0
        ):
            raise ValueError(
                "Collection limits must be positive; delay must be non-negative"
            )
        self.last_run: Optional[ScrapeRunResult] = None
        self.base_url = base_url if base_url is not None else settings.base_url
        self.delay = delay
        self.adapter: SourceAdapter = adapter or OxylabsAdapter()
        self.page_budget = page_budget
        self.run_timeout = run_timeout
        self.max_attempts = max_att
        self.timeout = req_timeout
        self.on_page = on_page

    def page_url(self, number: int) -> str:
        if hasattr(self.adapter, "page_url"):
            return self.adapter.page_url(self.base_url, number)
        return default_page_url(self.base_url, number)

    def new_run(self, max_pages: Optional[int], kind: str) -> ScrapeRunResult:
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be positive")
        self.last_run = ScrapeRunResult(
            self.base_url,
            max_pages,
            kind,
            source_name=getattr(self.adapter, "name", "oxylabs"),
            configuration={
                "page_budget": self.page_budget,
                "run_timeout": self.run_timeout,
                "max_attempts": self.max_attempts,
                "timeout": self.timeout,
                "delay": self.delay,
                "adapter": getattr(self.adapter, "name", "oxylabs"),
                "delay_policy": "per-host sliding window",
            },
        )
        return self.last_run

    def close(self) -> None:  # noqa: B027
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


class AutoScraper(BaseScraper):
    """Try lightweight HTTP first; fall back to Playwright only on layout_unrecognized."""

    def __init__(self, base_url: Optional[str] = None, delay: float = 1.0, **kwargs):
        super().__init__(base_url, delay, **kwargs)
        self._active: Optional[BaseScraper] = None

    def scrape(self, max_pages: Optional[int] = None) -> ScrapeRunResult:
        from scrapingstore.transport.browser import BrowserScraper
        from scrapingstore.transport.http import StaticScraper

        static = StaticScraper(
            self.base_url,
            self.delay,
            adapter=self.adapter,
            page_budget=self.page_budget,
            run_timeout=self.run_timeout,
            max_attempts=self.max_attempts,
            timeout=self.timeout,
            on_page=self.on_page,
        )
        self._active = static
        try:
            probe = static.scrape(max_pages=1 if (max_pages or 2) > 1 else max_pages)
            needs_browser = (
                probe.status == "failed"
                and any(
                    "layout_unrecognized" in err
                    for page in probe.pages
                    for err in page.errors
                )
            )
            if not needs_browser:
                if max_pages == 1 or probe.stop_reason == "source_end":
                    self.last_run = probe
                    return probe
                # Static works! Collect full requested scope with static
                full = static.scrape(max_pages=max_pages)
                self.last_run = full
                return full
        finally:
            static.close()

        browser = BrowserScraper(
            self.base_url,
            self.delay,
            adapter=self.adapter,
            page_budget=self.page_budget,
            run_timeout=self.run_timeout,
            max_attempts=self.max_attempts,
            timeout=self.timeout,
            on_page=self.on_page,
        )
        self._active = browser
        try:
            run = browser.scrape(max_pages=max_pages)
            self.last_run = run
            return run
        finally:
            browser.close()

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
