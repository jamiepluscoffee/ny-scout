"""Smalls Jazz Club adapter — HTML scraping (smallslive.com)."""
import re
from datetime import datetime

from ingestion.scrape_adapter import ScrapeAdapter
from ingestion.base import EventDict


class Adapter(ScrapeAdapter):
    """Scrape smallslive.com/tickets/ for upcoming events.

    Note: This site is JavaScript-heavy. If requests+BS4 returns no events,
    a Playwright-based fallback would be needed.
    """

    VENUE_NAME = "Smalls Jazz Club"

    def fetch_raw(self) -> str:
        return self.fetch_html()

    def parse(self, raw: str) -> list[EventDict]:
        soup = self.soup(raw)
        events = []

        # Try to find event cards/listings
        # SmallsLive uses various class names for event listings
        event_blocks = (
            soup.select(".event-card, .ticket-event, .event-item, .show-card")
            or soup.select("[class*='event'], [class*='show'], [class*='ticket']")
            or soup.select("article, .card")
        )

        for block in event_blocks:
            title = ""
            date_str = ""
            time_str = ""
            ticket_url = ""
            price_text = ""

            # Title / artist
            title_el = block.select_one(
                "h2, h3, h4, .event-title, .show-title, .artist-name, "
                "[class*='title'], [class*='artist']"
            )
            if title_el:
                title = title_el.get_text(strip=True)

            # Date
            date_el = block.select_one(
                ".date, .event-date, time, [class*='date']"
            )
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            # Time
            time_el = block.select_one("[class*='time']")
            if time_el:
                time_str = time_el.get_text(strip=True)

            # Price
            price_el = block.select_one("[class*='price'], .price")
            if price_el:
                price_text = price_el.get_text(strip=True)

            # Ticket link
            link = block.select_one("a[href]")
            if link:
                href = link.get("href", "")
                if href.startswith("/"):
                    href = "https://www.smallslive.com" + href
                ticket_url = href
                # If no title, use link text
                if not title:
                    title = link.get_text(strip=True)

            if not title:
                continue

            # Parse date
            combined = f"{date_str} {time_str}".strip()
            start_dt = self.parse_datetime(combined) or self.parse_datetime(date_str)
            if not start_dt:
                # Try extracting date from any text in the block
                block_text = block.get_text()
                date_match = re.search(
                    r'(\w+ \d{1,2},?\s*\d{4})', block_text
                )
                if date_match:
                    start_dt = self.parse_datetime(date_match.group(1))
            if not start_dt:
                continue

            # Parse price
            price_min = None
            price_match = re.search(r'\$(\d+(?:\.\d{2})?)', price_text)
            if price_match:
                price_min = float(price_match.group(1))

            event_id = self.make_event_id("smalls", f"{title[:40]}:{start_dt.date()}")

            events.append(EventDict(
                source_event_id=event_id,
                title=title,
                start_dt=start_dt,
                venue_name=self.VENUE_NAME,
                address="183 W 10th St, New York, NY 10014",
                price_min=price_min,
                ticket_url=ticket_url or "https://www.smallslive.com/tickets/",
                category="jazz",
                entities=[{"type": "artist", "value": title}],
            ))

        if not events:
            self.logger.warning(
                "No events parsed from SmallsLive. Site may require JavaScript "
                "rendering (Playwright). Raw HTML length: %d", len(raw)
            )

        return events
