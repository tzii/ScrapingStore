"""Capture README images from the archived demo, without collecting new data.

Run ``python -m scripts.refresh_demo`` first if templates have changed, then
``python -m scripts.capture_readme``. Requires Playwright Chromium and internet
access for the demo's web fonts and CDN libraries.
"""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1400},
            device_scale_factor=1,
            color_scheme="dark",
            reduced_motion="reduce",
            locale="en-GB",
            timezone_id="UTC",
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "requestfailed",
            lambda request: errors.append(f"{request.url}: {request.failure}"),
        )
        try:
            page.goto((ROOT / "docs/index.html").as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_function(
                "typeof Chart !== 'undefined' && Chart.getChart('priceChart')"
                " && Chart.getChart('availChart')"
            )
            expect(page.locator("#grid-table tbody tr")).to_have_count(12)
            expect(page.locator("[x-show='showSplash']")).to_be_hidden()
            expect(page.locator("#kpi-total")).to_have_text("3000")
            # Include the complete freshness panel below the charts.
            freshness = page.locator("#freshness").bounding_box()
            page.set_viewport_size(
                {
                    "width": 1440,
                    "height": round(freshness["y"] + freshness["height"] + 24),
                }
            )
            page.screenshot(
                path=str(ASSETS / "dashboard_modern.png"), animations="disabled"
            )

            page.get_by_label("Search catalog").fill("Mario")
            page.get_by_label("Filter by availability").select_option("In Stock")
            page.get_by_label("Minimum price").fill("50")
            page.get_by_label("Maximum price").fill("90")
            expect(page.locator("#grid-table tbody tr")).to_have_count(12)
            expect(page.locator("#grid-table tbody tr").first).to_contain_text("Mario")
            expect(page.locator("#grid-table tbody")).to_contain_text(
                "Observed over 7 days ago"
            )
            page.locator("#catalog").screenshot(
                path=str(ASSETS / "dashboard_catalog.jpg"),
                type="jpeg",
                quality=90,
                animations="disabled",
            )

            page.set_viewport_size({"width": 1440, "height": 1000})
            page.goto(
                (ROOT / "docs/dashboard_terminal.html").as_uri(),
                wait_until="networkidle",
            )
            page.evaluate("document.fonts.ready")
            expect(page.locator("#t-count")).to_have_text("3000")
            expect(page.locator("#log-feed")).to_contain_text(
                "Observed over 7 days ago"
            )
            expect(page.locator("#term-output")).to_contain_text("Outcome not captured")
            page.wait_for_function(
                "document.getElementById('nav-clock').textContent !== '--:--:--'"
            )
            page.screenshot(
                path=str(ASSETS / "dashboard_terminal.png"), animations="disabled"
            )
            if errors:
                raise RuntimeError("Dashboard JavaScript errors: " + "; ".join(errors))
        finally:
            context.close()
            browser.close()
    print("Captured modern overview, filtered catalog and terminal screenshots.")


if __name__ == "__main__":
    run()
