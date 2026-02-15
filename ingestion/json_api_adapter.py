"""Generic JSON API fetcher."""
import requests

from ingestion.base import BaseAdapter


class JSONAPIAdapter(BaseAdapter):
    """Base for sources with structured JSON APIs."""

    def fetch_json(self, url: str, params: dict = None, headers: dict = None) -> dict:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
