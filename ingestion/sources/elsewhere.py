"""Elsewhere Brooklyn adapter.

Elsewhere (elsewhere.club) embeds event data in Next.js __NEXT_DATA__
as server-rendered JSON. Each event has structured artist, venue (room),
genre, and ticket data. Paginates via ?page=N query param.
"""
from __future__ import annotations

import json
import logging

import requests
from bs4 import BeautifulSoup

from ingestion.base import BaseAdapter, EventDict

logger = logging.getLogger(__name__)

MAX_PAGES = 3  # ~36 events/page × 3 = ~108 events, covers ~3 months


class Adapter(BaseAdapter):

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def fetch_raw(self) -> str:
        """Fetch all pages and return combined JSON string."""
        all_events = []
        for page in range(1, MAX_PAGES + 1):
            url = f"{self.url}?page={page}"
            resp = requests.get(url, headers=self.HEADERS, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                logger.warning(f"No __NEXT_DATA__ on page {page}")
                break

            data = json.loads(script.string)
            event_data = data["props"]["pageProps"]["initialEventData"]
            all_events.extend(event_data.get("events", []))

            if not event_data.get("hasNextPage"):
                break

        logger.info(f"Fetched {len(all_events)} events across {page} pages")
        return json.dumps(all_events)

    def parse(self, raw: str) -> list[EventDict]:
        events_data = json.loads(raw)
        events = []

        for item in events_data:
            name = item.get("name", "").strip()
            start_str = item.get("start_date", "")
            start_dt = self.parse_datetime(start_str)
            if not name or not start_dt:
                continue

            end_dt = self.parse_datetime(item.get("end_date", ""))

            # Room names (Zone One, The Hall, Rooftop, etc.)
            rooms = item.get("venues", [])
            room_str = ", ".join(rooms) if rooms else ""
            venue_name = f"Elsewhere ({room_str})" if room_str else "Elsewhere"

            # Artists
            entities = []
            for artist in item.get("artists", []):
                if artist:
                    entities.append({"type": "artist", "value": artist})

            # If no artists parsed from the list, try splitting the event name
            if not entities and name:
                entities.append({"type": "artist", "value": name})

            # Price
            price = item.get("representative_ticket_price")
            price_min = float(price) if price else None

            event_id = self.make_event_id(
                self.name,
                f"elsewhere:{item.get('id', '')}:{start_str[:10]}"
            )

            events.append(EventDict(
                source_event_id=event_id,
                title=name,
                description=item.get("description", ""),
                start_dt=start_dt,
                end_dt=end_dt,
                venue_name=venue_name,
                address=item.get("address", "599 Johnson Avenue, Brooklyn, NY 11237"),
                price_min=price_min,
                ticket_url=item.get("ticket_url", ""),
                category="concert",
                raw_json=item,
                entities=entities,
            ))

        logger.info(f"Parsed {len(events)} events from Elsewhere")
        return events
