"""Generic BeautifulSoup scraper base."""
import requests
from bs4 import BeautifulSoup

from ingestion.base import BaseAdapter


class ScrapeAdapter(BaseAdapter):
    """Base for sources requiring HTML scraping."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def fetch_html(self, url: str = None) -> str:
        resp = requests.get(url or self.url, headers=self.HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")
