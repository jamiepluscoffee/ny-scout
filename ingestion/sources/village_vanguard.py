"""Village Vanguard adapter — HTML scraping."""
import re
from datetime import datetime, timedelta

from ingestion.scrape_adapter import ScrapeAdapter
from ingestion.base import EventDict


class Adapter(ScrapeAdapter):
    """Scrape the Village Vanguard schedule page."""

    VENUE_NAME = "Village Vanguard"

    def fetch_raw(self) -> str:
        return self.fetch_html()

    def parse(self, raw: str) -> list[EventDict]:
        soup = self.soup(raw)
        events = []

        # Village Vanguard typically shows weekly residencies.
        # Look for event/schedule blocks in the page.
        # The site structure varies, so we try multiple selectors.

        # Try common patterns for event listings
        event_blocks = (
            soup.select(".event-listing, .schedule-item, .event, .entry")
            or soup.select("article")
            or soup.select(".content-wrapper h2, .content-wrapper h3")
        )

        # If structured blocks aren't found, try to parse the main content
        if not event_blocks:
            event_blocks = self._parse_text_schedule(soup)

        for i, block in enumerate(event_blocks):
            title = ""
            date_str = ""
            description = ""

            if hasattr(block, "select"):
                # Try to find title
                title_el = (
                    block.select_one("h2, h3, h4, .title, .event-title, .artist")
                )
                if title_el:
                    title = title_el.get_text(strip=True)
                elif hasattr(block, "get_text"):
                    title = block.get_text(strip=True)

                # Try to find date
                date_el = block.select_one(".date, .event-date, time")
                if date_el:
                    date_str = date_el.get_text(strip=True)
                    if date_el.get("datetime"):
                        date_str = date_el["datetime"]

                # Description
                desc_el = block.select_one(".description, .event-description, p")
                if desc_el:
                    description = desc_el.get_text(strip=True)
            else:
                title = str(block.get("title", ""))
                date_str = str(block.get("date", ""))

            if not title:
                continue

            # Parse date — if no date found, estimate from current week
            start_dt = self.parse_datetime(date_str)
            if not start_dt:
                # Default to upcoming week at 8:30 PM (standard Vanguard set time)
                today = datetime.now().replace(hour=20, minute=30, second=0, microsecond=0)
                start_dt = today + timedelta(days=i)

            # Try to extract set times from the text
            set_times = re.findall(r'(\d{1,2}(?::\d{2})?\s*(?:PM|AM|pm|am))', title + " " + description)
            if set_times and not self.parse_datetime(date_str):
                # We found explicit set times
                pass

            ticket_url = ""
            link = block.select_one("a[href]") if hasattr(block, "select_one") else None
            if link:
                href = link.get("href", "")
                if href.startswith("/"):
                    href = "https://villagevanguard.com" + href
                ticket_url = href

            event_id = self.make_event_id("village_vanguard", f"{title[:40]}:{start_dt.date()}")

            events.append(EventDict(
                source_event_id=event_id,
                title=title,
                description=description,
                start_dt=start_dt,
                venue_name=self.VENUE_NAME,
                address="178 7th Ave S, New York, NY 10014",
                ticket_url=ticket_url or "https://villagevanguard.com",
                category="jazz",
                entities=[{"type": "artist", "value": title}],
            ))

        return events

    def _parse_text_schedule(self, soup):
        """Fallback: extract event info from raw text content."""
        results = []
        # Look for the main content area
        main = soup.select_one("main, .main-content, #content, body")
        if not main:
            return results

        # Find headings that might be artist names
        for heading in main.find_all(["h1", "h2", "h3", "h4"]):
            text = heading.get_text(strip=True)
            if len(text) > 3 and not text.lower().startswith(("menu", "nav", "footer")):
                results.append(heading)
        return results
