"""Real Chromium collection against intercepted fixture pages."""

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.async_api import Browser

from scraper.product_scraper_browser import BrowserScraper
from tests.test_collection_integrity import card_html


@pytest.fixture
def browser_site(request, monkeypatch):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser")
    original = Browser.new_context
    calls = {}
    contexts = []

    async def respond(route):
        number = int(parse_qs(urlsplit(route.request.url).query).get("page", ["1"])[0])
        calls[number] = calls.get(number, 0) + 1
        if number == 2 and calls[number] == 1:
            await route.fulfill(
                status=503, body="Temporary error", headers={"Retry-After": "0"}
            )
        elif number == 3:
            await route.fulfill(status=403, body="Access denied")
        elif number == 5:
            await route.fulfill(
                body='<p data-empty="true">Empty catalog</p>', content_type="text/html"
            )
        else:
            import json

            content = card_html(
                identity=str(number), price=None if number == 1 else "19,99 €"
            )
            html = f"<body><script>setTimeout(() => document.body.innerHTML = {json.dumps(content)}, 100)</script></body>"
            await route.fulfill(body=html, content_type="text/html")

    async def new_context(browser, **kwargs):
        context = await original(browser, **kwargs)
        contexts.append(context)
        await context.route("**/*", respond)
        return context

    monkeypatch.setattr(Browser, "new_context", new_context)
    return calls, contexts


def test_browser_collects_javascript_and_retains_http_failures(browser_site):
    calls, contexts = browser_site
    scraper = BrowserScraper(
        "https://fixture.test/products", delay=0, max_attempts=2, timeout=5
    )
    run = scraper.scrape(max_pages=5)
    assert run.status == "partial"
    assert run.stop_reason == "source_end"
    assert run.manifest()["pages_attempted"] == 5
    assert run.manifest()["pages_failed"] == 1
    assert run.manifest()["pages_succeeded"] == 4
    assert len(run.products) == 3
    assert run.products[0].price is None
    assert calls[2] == 2 and calls[3] == 1
    assert contexts[0].pages == []


def test_sync_wrapper_directs_async_callers_to_public_async_method():
    async def active_loop():
        with pytest.raises(RuntimeError, match="scrape_async"):
            BrowserScraper("https://fixture.test").scrape(1)

    asyncio.run(active_loop())


def test_browser_changed_layout_is_failure(request, monkeypatch):
    if not request.config.getoption("--run-browser"):
        pytest.skip("Use --run-browser")
    original = Browser.new_context

    async def new_context(browser, **kwargs):
        context = await original(browser, **kwargs)
        await context.route(
            "**/*",
            lambda route: route.fulfill(
                body="<body>Unexpected layout</body>", content_type="text/html"
            ),
        )
        return context

    monkeypatch.setattr(Browser, "new_context", new_context)
    run = BrowserScraper("https://fixture.test", delay=0, timeout=0.3).scrape(1)
    assert run.status == "failed"
    assert "render_timeout" in run.pages[0].errors[0]


def test_deadline_retains_completed_pages_and_cancels_pending_work():
    from unittest.mock import AsyncMock
    import time
    from models import Product
    from scraper.results import PageResult

    async def scenario():
        scraper = BrowserScraper("https://fixture.test", delay=0)
        run = scraper.new_run(2, "browser")
        cancelled = []

        async def collect(context, number, semaphore, deadline):
            if number == 1:
                return PageResult(
                    1,
                    "https://fixture.test",
                    status="success",
                    products=[
                        Product(
                            name="Completed", price=0, source_url="https://fixture.test"
                        )
                    ],
                )
            try:
                await asyncio.Future()
            finally:
                cancelled.append(number)

        scraper._scrape_single_page = collect
        reason = await scraper._collect_pages(AsyncMock(), run, time.monotonic() + 0.05)
        run.finish(reason)
        assert run.status == "partial" and run.stop_reason == "deadline"
        assert len(run.products) == 1
        assert run.manifest()["pages_attempted"] == 2
        assert cancelled == [2]

    asyncio.run(scenario())


def test_page_is_closed_when_async_collection_is_cancelled():
    from unittest.mock import AsyncMock
    import time

    async def scenario():
        context = AsyncMock()
        page = context.new_page.return_value
        page.goto.side_effect = asyncio.CancelledError
        scraper = BrowserScraper("https://fixture.test")
        with pytest.raises(asyncio.CancelledError):
            await scraper._scrape_single_page(
                context, 1, asyncio.Semaphore(1), time.monotonic() + 10
            )
        page.close.assert_awaited_once()

    asyncio.run(scenario())
