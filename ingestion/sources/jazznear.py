"""JazzNearYou adapter — JSON-LD MusicEvent extraction."""
import json
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from ingestion.base import BaseAdapter, EventDict


class Adapter(BaseAdapter):
    """Extract Schema.org MusicEvent JSON-LD from jazznearyou.com."""

    def fetch_raw(self) -> str:
        now = datetime.utcnow()
        url = (
            f"{self.url}"
            f"?searchmonth={now.month:02d}"
            f"&searchyear={now.year}"
        )
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp.raise_for_status()
        return resp.text

    def parse(self, raw: str) -> list[EventDict]:
        soup = BeautifulSoup(raw, "html.parser")
        events = []

        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string)
            except (json.JSONDecodeError, TypeError):
                continue

            # Handle both single objects and arrays
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") != "MusicEvent":
                    continue

                title = item.get("name", "")
                start_str = item.get("startDate", "")
                start_dt = self.parse_datetime(start_str)
                if not start_dt:
                    continue

                end_str = item.get("endDate", "")
                end_dt = self.parse_datetime(end_str)

                location = item.get("location", {})
                venue_name = location.get("name", "Unknown Venue")
                address_obj = location.get("address", {})
                if isinstance(address_obj, dict):
                    address = address_obj.get("streetAddress", "")
                else:
                    address = str(address_obj)

                ticket_url = item.get("url", "")

                # Extract performers
                entities = []
                performers = item.get("performer", [])
                if not isinstance(performers, list):
                    performers = [performers]
                for perf in performers:
                    if isinstance(perf, dict):
                        entities.append({"type": "artist", "value": perf.get("name", "")})
                    elif isinstance(perf, str):
                        entities.append({"type": "artist", "value": perf})

                # Offers / price
                offers = item.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price_min = offers.get("price") or offers.get("lowPrice")
                price_max = offers.get("highPrice")

                event_id = self.make_event_id(
                    "jazznear",
                    f"{venue_name}:{start_str}:{title[:30]}"
                )

                events.append(EventDict(
                    source_event_id=event_id,
                    title=title,
                    description=item.get("description", ""),
                    start_dt=start_dt,
                    end_dt=end_dt,
                    venue_name=venue_name,
                    address=address,
                    price_min=float(price_min) if price_min else None,
                    price_max=float(price_max) if price_max else None,
                    ticket_url=ticket_url,
                    category="jazz",
                    raw_json=item,
                    entities=entities,
                ))
        return events
