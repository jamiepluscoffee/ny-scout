"""Ticketmaster Discovery API adapter."""
import os
from datetime import datetime, timedelta

from ingestion.json_api_adapter import JSONAPIAdapter
from ingestion.base import EventDict


class Adapter(JSONAPIAdapter):
    """Fetch NYC music/arts events from Ticketmaster Discovery API v2."""

    BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
    PAGE_SIZE = 200  # Ticketmaster max per page
    MAX_PAGES = 5    # API caps at 1000 results (5 * 200)

    def __init__(self, source_cfg: dict):
        super().__init__(source_cfg)
        self._backfill = False

    def set_backfill(self, enabled: bool):
        self._backfill = enabled

    def _base_params(self, api_key: str) -> dict:
        now = datetime.utcnow()
        start = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        days = 90 if self._backfill else 90
        end = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "apikey": api_key,
            "latlong": "40.7128,-74.0060",
            "radius": "15",
            "unit": "miles",
            "classificationName": "music,arts",
            "startDateTime": start,
            "endDateTime": end,
            "size": self.PAGE_SIZE,
            "sort": "onSaleStartDate,asc",
        }

    def fetch_raw(self) -> dict:
        api_key = os.environ.get("TICKETMASTER_API_KEY", "")
        if not api_key:
            self.logger.warning("TICKETMASTER_API_KEY not set, skipping")
            return {"_embedded": {"events": []}}

        params = self._base_params(api_key)
        max_pages = self.MAX_PAGES if self._backfill else 1

        all_events = []
        for page in range(max_pages):
            params["page"] = page
            data = self.fetch_json(self.BASE_URL, params=params)
            events = data.get("_embedded", {}).get("events", [])
            all_events.extend(events)

            page_info = data.get("page", {})
            total_pages = page_info.get("totalPages", 1)
            self.logger.info(
                f"Ticketmaster page {page + 1}/{min(max_pages, total_pages)}: "
                f"{len(events)} events"
            )

            if page + 1 >= total_pages:
                break

        return {"_embedded": {"events": all_events}}

    def parse(self, raw: dict) -> list[EventDict]:
        events = []
        embedded = raw.get("_embedded", {})
        for item in embedded.get("events", []):
            event_id = item.get("id", "")
            title = item.get("name", "")
            start_info = item.get("dates", {}).get("start", {})
            start_str = start_info.get("dateTime") or start_info.get("localDate", "")
            start_dt = self.parse_datetime(start_str)
            if not start_dt:
                continue

            # Venue info
            venues = item.get("_embedded", {}).get("venues", [])
            venue = venues[0] if venues else {}
            venue_name = venue.get("name", "Unknown Venue")
            address_parts = []
            if venue.get("address", {}).get("line1"):
                address_parts.append(venue["address"]["line1"])
            if venue.get("city", {}).get("name"):
                address_parts.append(venue["city"]["name"])
            address = ", ".join(address_parts)

            # Price
            price_ranges = item.get("priceRanges", [])
            price_min = price_ranges[0].get("min") if price_ranges else None
            price_max = price_ranges[0].get("max") if price_ranges else None

            # Category
            classifications = item.get("classifications", [])
            genre = ""
            if classifications:
                genre = classifications[0].get("genre", {}).get("name", "").lower()

            category = "jazz" if "jazz" in genre else "concert"

            ticket_url = item.get("url", "")

            entities = []
            attractions = item.get("_embedded", {}).get("attractions", [])
            for att in attractions:
                entities.append({"type": "artist", "value": att.get("name", "")})

            events.append(EventDict(
                source_event_id=self.make_event_id("ticketmaster", event_id),
                title=title,
                description=item.get("info", ""),
                start_dt=start_dt,
                end_dt=None,
                venue_name=venue_name,
                address=address,
                price_min=price_min,
                price_max=price_max,
                ticket_url=ticket_url,
                category=category,
                raw_json=item,
                entities=entities,
            ))
        return events
