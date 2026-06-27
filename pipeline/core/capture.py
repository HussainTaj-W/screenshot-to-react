"""Playwright screenshot capture of the built page at the inferred viewport.

Uses the **async** Playwright API because the verify graph runs inside an
asyncio event loop (the sync API raises inside a running loop).
"""

from __future__ import annotations


async def capture_page_async(url: str, *, viewport_width: int, viewport_height: int = 900) -> bytes:
    """Navigate to ``url`` and return a full-page PNG screenshot (async)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height}
            )
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(400)
            return await page.screenshot(full_page=True)
        finally:
            await browser.close()


def capture_page(url: str, *, viewport_width: int, viewport_height: int = 900) -> bytes:
    """Sync wrapper for non-async callers/tests (must NOT be called in a loop).

    Inside the async graph, call ``capture_page_async`` directly.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height})
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(400)
            return page.screenshot(full_page=True)
        finally:
            browser.close()
