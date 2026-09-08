"""Playwright acquisition with bounded concurrency and explicit run outcomes."""

import asyncio
import time
from typing import Optional

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from config import DEFAULT_TIMEOUT, USER_AGENT_FALLBACK
from scraper.base import BaseScraper, TRANSIENT_STATUSES, retry_delay
from scraper.parsing import EMPTY_TEXT, READY_SELECTOR, parse_page
from scraper.results import PageResult, ScrapeRunResult


class BrowserScraper(BaseScraper):
    def scrape(self, max_pages: Optional[int] = None) -> ScrapeRunResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.scrape_async(max_pages))
        raise RuntimeError(
            "Use await scraper.scrape_async() inside an active event loop"
        )

    async def scrape_async(self, max_pages: Optional[int] = None) -> ScrapeRunResult:
        run = self.new_run(max_pages, "browser")
        deadline = time.monotonic() + self.run_timeout
        browser = None
        context = None
        try:
            async with async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(
                        headless=True,
                        timeout=max(
                            1, min(DEFAULT_TIMEOUT, self.remaining(deadline)) * 1000
                        ),
                    )
                    context = await asyncio.wait_for(
                        browser.new_context(user_agent=USER_AGENT_FALLBACK),
                        timeout=self.remaining(deadline),
                    )
                    reason = await self._collect_pages(context, run, deadline)
                    run.finish(reason)
                finally:
                    for resource in (context, browser):
                        if resource:
                            try:
                                await resource.close()
                            except Exception as exc:
                                run.errors.append(f"cleanup_error: {exc}")
        except asyncio.CancelledError:
            run.finish("cancelled")
            raise
        except Exception as exc:
            run.errors.append(f"{type(exc).__name__}: {exc}")
            run.finish("setup_or_browser_error")
        return run

    async def _collect_pages(
        self, context: BrowserContext, run: ScrapeRunResult, deadline: float
    ) -> str:
        limit = min(run.requested_pages or self.page_budget, self.page_budget)
        semaphore = asyncio.Semaphore(3)
        seen: set[str] = set()
        for start in range(1, limit + 1, 3):
            if not self.remaining(deadline):
                return "deadline"
            numbers = list(range(start, min(start + 3, limit + 1)))
            completed: list[PageResult] = []

            async def collect(number: int) -> None:
                result = await self._scrape_single_page(
                    context, number, semaphore, deadline
                )
                completed.append(result)
                run.pages.append(result)

            try:
                await asyncio.wait_for(
                    asyncio.gather(*(collect(n) for n in numbers)),
                    timeout=self.remaining(deadline),
                )
            except asyncio.CancelledError:
                finished = {page.number for page in completed}
                run.pages.extend(
                    PageResult(
                        n, self.page_url(n), errors=["cancelled during collection"]
                    )
                    for n in numbers
                    if n not in finished
                )
                run.pages.sort(key=lambda p: p.number)
                raise
            except asyncio.TimeoutError:
                finished = {page.number for page in completed}
                completed.extend(
                    PageResult(n, self.page_url(n), errors=["run deadline exceeded"])
                    for n in numbers
                    if n not in finished
                )
                run.pages.extend(
                    page
                    for page in completed
                    if page.number not in {p.number for p in run.pages}
                )
                run.pages.sort(key=lambda p: p.number)
                return "deadline"
            run.pages.sort(key=lambda p: p.number)
            reason = None
            for page in sorted(completed, key=lambda p: p.number):
                page_reason = self.stopping_reason(run, seen, page)
                reason = reason or page_reason
            if reason:
                return reason
            if start + 3 <= limit:
                await asyncio.sleep(min(self.delay, self.remaining(deadline)))
        return (
            "page_limit"
            if run.requested_pages and run.requested_pages <= self.page_budget
            else "page_budget"
        )

    async def _scrape_single_page(
        self,
        context: BrowserContext,
        number: int,
        semaphore: asyncio.Semaphore,
        deadline: float,
    ) -> PageResult:
        async with semaphore:
            result = PageResult(number, self.page_url(number))
            page = None
            try:
                page = await context.new_page()
                result = await self._navigate(page, result, deadline)
                return result
            except Exception as exc:
                result.errors = [f"{type(exc).__name__}: {exc}"]
                return result
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception as exc:
                        result.errors.append(f"page_cleanup_error: {exc}")
                        result.status = "partial" if result.products else "failed"

    async def _navigate(
        self, page: Page, result: PageResult, deadline: float
    ) -> PageResult:
        for attempt in range(1, self.max_attempts + 1):
            result.attempts = attempt
            if not self.remaining(deadline):
                result.errors = ["run deadline exceeded"]
                return result
            retry_after = None
            try:
                response = await page.goto(
                    result.url,
                    timeout=max(1, min(self.timeout, self.remaining(deadline)) * 1000),
                    wait_until="domcontentloaded",
                )
                if response is None:
                    result.errors = ["navigation returned no HTTP response"]
                    return result
                result.http_status = response.status
                if 200 <= response.status < 300:
                    return await self._read_rendered(page, result, deadline)
                result.errors = [f"HTTP {response.status}"]
                if response.status not in TRANSIENT_STATUSES:
                    return result
                retry_after = response.headers.get("retry-after")
            except PlaywrightError as exc:
                result.errors = [f"navigation_error: {exc}"]
                if not self._transient_error(exc):
                    return result
            if attempt < self.max_attempts and not await self._pause_retry(
                result, retry_after, deadline
            ):
                return result
        return result

    async def _pause_retry(
        self, result: PageResult, retry_after: Optional[str], deadline: float
    ) -> bool:
        pause = retry_delay(result.attempts, retry_after)
        if pause >= self.remaining(deadline):
            result.errors.append("retry exceeds remaining run deadline")
            return False
        await asyncio.sleep(pause)
        return True

    @staticmethod
    def _transient_error(error: PlaywrightError) -> bool:
        return isinstance(error, PlaywrightTimeoutError) or any(
            code in str(error)
            for code in (
                "ERR_CONNECTION_RESET",
                "ERR_CONNECTION_CLOSED",
                "ERR_TIMED_OUT",
                "ERR_NAME_NOT_RESOLVED",
            )
        )

    async def _read_rendered(
        self, page: Page, result: PageResult, deadline: float
    ) -> PageResult:
        try:
            await page.wait_for_function(
                "args => document.querySelector(args.selector) || "
                "document.body.innerText.includes(args.empty)",
                arg={"selector": READY_SELECTOR, "empty": EMPTY_TEXT},
                timeout=max(1, min(self.timeout, self.remaining(deadline)) * 1000),
            )
        except PlaywrightTimeoutError:
            result.errors = [
                "render_timeout: no product cards or confirmed empty state"
            ]
            return result
        parsed = parse_page(await page.content(), result.url, result.number)
        parsed.attempts = result.attempts
        parsed.http_status = result.http_status
        return parsed
