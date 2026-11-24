"""Capture the README screenshots from the offline report in docs/ (no network needed).

Run from repository root after `python -m scripts.refresh_demo`:
    python -m scripts.capture_readme
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
REPORT = (ROOT / "docs/index.html").as_uri()


def _bottom(page, selector: str) -> float:
    box = page.locator(selector).bounding_box()
    return box["y"] + box["height"]


def run() -> None:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for scheme in ("light", "dark"):
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    color_scheme=scheme,
                    reduced_motion="reduce",
                    locale="en-GB",
                    timezone_id="UTC",
                )
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(REPORT, wait_until="load")
                page.wait_for_selector("#grid tbody tr")

                if scheme == "light":
                    # Headline, controls and the first rows of the run grid.
                    page.screenshot(
                        path=str(ASSETS / "report.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 1000},
                        full_page=True,
                    )
                    # The headline numbers filter the grid.
                    page.locator('#lede button[data-ev="drop"]').click()
                    page.screenshot(
                        path=str(ASSETS / "report_dropped.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": _bottom(page, "#grid") + 24},
                        full_page=True,
                    )
                else:
                    lower = page.locator("#lower").bounding_box()
                    page.screenshot(
                        path=str(ASSETS / "report_dark.png"),
                        clip={
                            "x": 0,
                            "y": lower["y"] - 24,
                            "width": 1280,
                            "height": lower["height"] + 48,
                        },
                        full_page=True,
                    )
                context.close()
        finally:
            browser.close()
    if errors:
        raise RuntimeError("Report JavaScript errors: " + "; ".join(errors))
    print("Captured report.png, report_dropped.png and report_dark.png in assets/.")


if __name__ == "__main__":
    run()
