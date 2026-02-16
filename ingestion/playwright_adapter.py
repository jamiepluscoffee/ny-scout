"""Playwright-based scraper for JavaScript-rendered sites."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ingestion.base import BaseAdapter


def fetch_with_playwright(url: str, wait_for: str = "networkidle",
                          timeout: int = 15000, extra_wait: int = 2000) -> str:
    """Standalone function to fetch a URL with Playwright headless browser."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        try:
            page.goto(url, wait_until=wait_for, timeout=timeout)
            page.wait_for_timeout(extra_wait)
            html = page.content()
        finally:
            browser.close()
    return html


class PlaywrightAdapter(BaseAdapter):
    """Base for sources requiring JavaScript rendering.

    Uses Playwright with headless Chromium to render the page,
    then provides the fully-rendered HTML for parsing with BeautifulSoup.
    """

    WAIT_FOR = "networkidle"  # Wait strategy: "networkidle", "domcontentloaded", "load"
    WAIT_TIMEOUT = 15000      # Max ms to wait for page to settle
    EXTRA_WAIT = 2000         # Extra ms after load to let JS finish rendering

    def fetch_html(self, url: str = None) -> str:
        """Fetch a URL using Playwright headless browser."""
        from playwright.sync_api import sync_playwright

        target_url = url or self.url

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            try:
                page.goto(target_url, wait_until=self.WAIT_FOR,
                          timeout=self.WAIT_TIMEOUT)
                # Extra wait for JS rendering to complete
                page.wait_for_timeout(self.EXTRA_WAIT)
                html = page.content()
            finally:
                browser.close()

        return html

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")
