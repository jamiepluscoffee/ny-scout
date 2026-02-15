"""Poster House adapter — HTML scraping."""
import re
from datetime import datetime

from ingestion.scrape_adapter import ScrapeAdapter
from ingestion.base import EventDict


class Adapter(ScrapeAdapter):
    """Scrape posterhouse.org/events for upcoming events and exhibitions."""

    VENUE_NAME = "Poster House"

    def fetch_raw(self) -> str:
        return self.fetch_html()

    def parse(self, raw: str) -> list[EventDict]:
        soup = self.soup(raw)
        events = []

        # Look for event listings on the /events page
        event_blocks = (
            soup.select(".event-card, .event-item, .event-listing")
            or soup.select("article, .card, .post-item")
            or soup.select("[class*='event']")
        )

        for block in event_blocks:
            title = ""
            date_str = ""
            event_type = ""
            ticket_url = ""
            description = ""

            # Title
            title_el = block.select_one("h2, h3, h4, .title, [class*='title']")
            if title_el:
                title = title_el.get_text(strip=True)

            # Date
            date_el = block.select_one(
                ".date, time, [class*='date'], [class*='time']"
            )
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            # Event type / category tag
            type_el = block.select_one(
                ".event-type, .category, .tag, [class*='type'], [class*='category']"
            )
            if type_el:
                event_type = type_el.get_text(strip=True)

            # Description
            desc_el = block.select_one("p, .excerpt, .description, [class*='desc']")
            if desc_el:
                description = desc_el.get_text(strip=True)

            # Link
            link = block.select_one("a[href]")
            if link:
                href = link.get("href", "")
                if href.startswith("/"):
                    href = "https://posterhouse.org" + href
                ticket_url = href
                if not title:
                    title = link.get_text(strip=True)

            if not title:
                continue

            # Parse date
            start_dt = self.parse_datetime(date_str)
            if not start_dt:
                # Try to extract from block text
                block_text = block.get_text()
                date_match = re.search(
                    r'(\w+ \d{1,2},?\s*\d{4})', block_text
                )
                if date_match:
                    start_dt = self.parse_datetime(date_match.group(1))
            if not start_dt:
                # For exhibitions, they might not have specific dates
                # Use today as placeholder
                start_dt = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

            # Determine category
            type_lower = (event_type + " " + title).lower()
            if any(w in type_lower for w in ("exhibit", "display", "gallery", "poster")):
                category = "exhibition"
            else:
                category = "exhibition"  # Default for Poster House

            event_id = self.make_event_id("poster_house", f"{title[:40]}:{start_dt.date()}")

            events.append(EventDict(
                source_event_id=event_id,
                title=title,
                description=description,
                start_dt=start_dt,
                venue_name=self.VENUE_NAME,
                address="119 W 23rd St, New York, NY 10011",
                ticket_url=ticket_url or "https://posterhouse.org/events/",
                category=category,
                entities=[{"type": "exhibition", "value": title}],
            ))

        return events
