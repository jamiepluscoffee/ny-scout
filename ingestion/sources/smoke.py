"""Smoke Jazz Club adapter — HTML scrape from tickets.smokejazz.com."""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from ingestion.base import EventDict
from ingestion.scrape_adapter import ScrapeAdapter


class Adapter(ScrapeAdapter):
    """Scrape show listings from Smoke Jazz Club's ticket page."""

    VENUE_NAME = "Smoke Jazz Club"
    BASE_URL = "https://tickets.smokejazz.com"

    def fetch_raw(self) -> str:
        return self.fetch_html(self.url)

    def parse(self, raw: str) -> list[EventDict]:
        soup = self.soup(raw)
        cards = soup.select(".show-card")
        current_year = datetime.utcnow().year
        events = []

        for card in cards:
            perf = card.select_one(".performances")
            if not perf:
                continue

            # Title from h3
            h3 = perf.select_one("h3")
            title = h3.get_text(strip=True) if h3 else ""
            if not title:
                continue

            # Date from h4.day-of-week (e.g. "Sun, Feb 15")
            date_el = card.select_one("h4.day-of-week")
            date_str = date_el.get_text(strip=True) if date_el else ""
            if not date_str:
                continue

            start_dt = self.parse_datetime(f"{date_str}, {current_year}", "%a, %b %d, %Y")
            if not start_dt:
                continue

            # Default show time: 7pm (Smoke's typical first set)
            start_dt = start_dt.replace(hour=19)

            # Price from text (first dollar amount)
            text = perf.get_text(" ", strip=True)
            price_match = re.search(r"\$(\d+(?:\.\d{2})?)", text)
            price_min = float(price_match.group(1)) if price_match else None

            # Find highest price too
            all_prices = re.findall(r"\$(\d+(?:\.\d{2})?)", text)
            price_max = max(float(p) for p in all_prices) if all_prices else None

            # Ticket link
            ticket_url = ""
            for a in card.select("a[href*='/shows/']"):
                ticket_url = urljoin(self.BASE_URL, a["href"])
                break

            # Extract artist entities from title
            entities = [{"type": "artist", "value": title}]

            event_id = self.make_event_id(
                "smoke", f"{title}:{start_dt.strftime('%Y-%m-%d')}"
            )

            events.append(EventDict(
                source_event_id=event_id,
                title=title,
                start_dt=start_dt,
                venue_name=self.VENUE_NAME,
                address="2751 Broadway, New York, NY 10025",
                price_min=price_min,
                price_max=price_max,
                ticket_url=ticket_url,
                category="jazz",
                entities=entities,
            ))

        self.logger.info(f"Smoke: parsed {len(events)} shows")
        return events
