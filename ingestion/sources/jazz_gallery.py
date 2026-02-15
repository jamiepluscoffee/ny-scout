"""The Jazz Gallery adapter — ICS calendar extraction from Squarespace."""
import re

import requests
from bs4 import BeautifulSoup

from ingestion.ics_adapter import ICSAdapter
from ingestion.base import EventDict


class Adapter(ICSAdapter):
    """Scrape event page URLs from thejazzgallery.org/calendar, then fetch ICS for each."""

    VENUE_NAME = "The Jazz Gallery"

    def fetch_raw(self) -> list[str]:
        """Fetch calendar page and extract event page URLs."""
        resp = requests.get(self.url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        event_urls = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/calendar/" in href and href != "/calendar" and href != "/calendar/":
                if href.startswith("/"):
                    href = "https://www.thejazzgallery.org" + href
                # Strip any existing query params
                href = href.split("?")[0]
                event_urls.add(href)

        return list(event_urls)

    def parse(self, raw: list[str]) -> list[EventDict]:
        """For each event URL, fetch the ICS version and parse."""
        all_events = []
        for event_url in raw:
            ics_url = event_url + "?format=ical"
            try:
                ics_text = self.fetch_ics(ics_url)
                events = self.parse_ics(ics_text, "jazz_gallery", self.VENUE_NAME)
                # Add ticket URL from the event page
                for ev in events:
                    if not ev.get("ticket_url"):
                        ev["ticket_url"] = event_url
                all_events.extend(events)
            except Exception as e:
                self.logger.warning(f"Failed to fetch ICS for {event_url}: {e}")
                continue
        return all_events
