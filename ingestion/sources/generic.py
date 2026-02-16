"""Generic config-driven adapter for discovered sources.

Handles JSON-LD, ICS feed, and CSS selector extraction strategies
based on the 'extraction' block in the source's sources.yaml config.
Avoids needing custom Python code per discovered source.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ingestion.base import BaseAdapter, EventDict


class Adapter(BaseAdapter):
    """Config-driven adapter that picks an extraction strategy at runtime."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, source_config: dict):
        super().__init__(source_config)
        self.extraction = source_config.get("extraction", {})
        self.strategy = self.extraction.get("strategy", "json_ld")
        self.default_category = source_config.get("category", "")
        self.default_venue = self.extraction.get("default_venue", "")

    def fetch_raw(self) -> str:
        resp = requests.get(self.url, headers=self.HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text

    def parse(self, raw: str) -> list[EventDict]:
        if self.strategy == "json_ld":
            return self._parse_json_ld(raw)
        elif self.strategy == "ics":
            return self._parse_ics(raw)
        elif self.strategy == "css_selectors":
            return self._parse_css(raw)
        elif self.strategy == "follow_links":
            return self._parse_follow_links(raw)
        else:
            self.logger.warning(f"Unknown strategy '{self.strategy}', trying json_ld")
            return self._parse_json_ld(raw)

    def _parse_json_ld(self, html: str) -> list[EventDict]:
        """Extract events from Schema.org JSON-LD markup."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string)
            except (json.JSONDecodeError, TypeError):
                continue

            items = data if isinstance(data, list) else [data]
            for item in items:
                event = self._parse_jsonld_item(item)
                if event:
                    events.append(event)

        self.logger.info(f"JSON-LD: extracted {len(events)} events")
        return events

    def _parse_jsonld_item(self, item: dict) -> EventDict | None:
        """Parse a single JSON-LD item into an EventDict."""
        event_types = {"Event", "MusicEvent", "TheaterEvent",
                       "DanceEvent", "ExhibitionEvent", "SocialEvent"}
        item_type = item.get("@type", "")
        if item_type not in event_types:
            return None

        title = item.get("name", "").strip()
        start_str = item.get("startDate", "")
        start_dt = self.parse_datetime(start_str)
        if not title or not start_dt:
            return None

        end_dt = self.parse_datetime(item.get("endDate", ""))

        # Location
        location = item.get("location", {})
        if isinstance(location, dict):
            venue_name = location.get("name", self.default_venue or "Unknown Venue")
            address_obj = location.get("address", {})
            if isinstance(address_obj, dict):
                address = address_obj.get("streetAddress", "")
            else:
                address = str(address_obj)
        else:
            venue_name = self.default_venue or str(location)
            address = ""

        # Performers / entities
        entities = []
        performers = item.get("performer", [])
        if not isinstance(performers, list):
            performers = [performers]
        for perf in performers:
            if isinstance(perf, dict):
                name = perf.get("name", "")
                if name:
                    entities.append({"type": "artist", "value": name})
            elif isinstance(perf, str) and perf:
                entities.append({"type": "artist", "value": perf})

        # Price
        offers = item.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price_min = offers.get("price") or offers.get("lowPrice")
        price_max = offers.get("highPrice")

        ticket_url = item.get("url", "")

        # Category from config or infer from @type
        category = self.default_category
        if not category:
            type_to_cat = {
                "MusicEvent": "concert", "TheaterEvent": "theatre",
                "ExhibitionEvent": "exhibition", "DanceEvent": "concert",
            }
            category = type_to_cat.get(item_type, "")

        event_id = self.make_event_id(
            self.name,
            f"{venue_name}:{start_str}:{title[:30]}"
        )

        return EventDict(
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
            category=category,
            raw_json=item,
            entities=entities,
        )

    def _parse_ics(self, html: str) -> list[EventDict]:
        """Find and fetch an ICS feed linked from the page."""
        from ingestion.ics_adapter import ICSAdapter

        soup = BeautifulSoup(html, "html.parser")
        ics_url = None

        # Look for ICS feed links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".ics") or "ical" in href.lower() or "webcal" in href.lower():
                ics_url = urljoin(self.url, href)
                break

        # Also check <link> tags
        if not ics_url:
            for link in soup.find_all("link", href=True):
                if "calendar" in link.get("type", "").lower() or link["href"].endswith(".ics"):
                    ics_url = urljoin(self.url, link["href"])
                    break

        if not ics_url:
            self.logger.warning("ICS strategy selected but no .ics feed found on page")
            return []

        # Fetch and parse the ICS feed
        ics_adapter = ICSAdapter.__new__(ICSAdapter)
        ics_adapter.config = self.config
        ics_adapter.name = self.name
        ics_adapter.url = self.url
        ics_adapter.logger = self.logger

        ics_text = ics_adapter.fetch_ics(ics_url)
        venue_name = self.default_venue or self.name.replace("_", " ").title()
        return ics_adapter.parse_ics(ics_text, self.name, venue_name)

    def _parse_css(self, html: str) -> list[EventDict]:
        """Extract events using CSS selectors from config."""
        selectors = self.extraction
        container_sel = selectors.get("container", "article")
        title_sel = selectors.get("title", "h2, h3")
        date_sel = selectors.get("date", "time, .date, .event-date")
        venue_sel = selectors.get("venue", ".venue, .venue-name")

        soup = BeautifulSoup(html, "html.parser")
        events = []

        for block in soup.select(container_sel):
            title_el = block.select_one(title_sel)
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            date_el = block.select_one(date_sel)
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
            start_dt = self.parse_datetime(date_str)
            if not start_dt:
                continue

            venue_el = block.select_one(venue_sel)
            venue_name = (
                venue_el.get_text(strip=True) if venue_el
                else self.default_venue or "Unknown Venue"
            )

            # Try to find a link
            link_el = block.select_one("a[href]")
            ticket_url = urljoin(self.url, link_el["href"]) if link_el else ""

            event_id = self.make_event_id(
                self.name,
                f"{venue_name}:{date_str}:{title[:30]}"
            )

            events.append(EventDict(
                source_event_id=event_id,
                title=title,
                start_dt=start_dt,
                venue_name=venue_name,
                ticket_url=ticket_url,
                category=self.default_category,
            ))

        self.logger.info(f"CSS selectors: extracted {len(events)} events")
        return events

    def _parse_follow_links(self, html: str) -> list[EventDict]:
        """Follow event links on a listing page and extract from each sub-page.

        Config options in extraction block:
          link_pattern: regex to match event URLs (default: derived from URL path)
          max_pages: max sub-pages to fetch (default: 50)
          sub_strategy: how to extract from each sub-page (default: json_ld)
          fetch_delay: seconds between requests (default: 1)
        """
        soup = BeautifulSoup(html, "html.parser")
        link_pattern = self.extraction.get("link_pattern", "")
        max_pages = int(self.extraction.get("max_pages", 50))
        sub_strategy = self.extraction.get("sub_strategy", "json_ld")
        fetch_delay = float(self.extraction.get("fetch_delay", 1))

        # Build link pattern from URL if not configured
        if not link_pattern:
            parsed = urlparse(self.url)
            # e.g. /shows → matches /shows/some-event-slug
            base_path = parsed.path.rstrip("/")
            link_pattern = re.escape(base_path) + r"/[^/?#]+"

        # Collect unique event URLs from the listing page
        event_urls = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(self.url, href)
            # Strip query params and fragments for dedup
            clean = full_url.split("?")[0].split("#")[0]
            if clean in seen or clean == self.url.rstrip("/"):
                continue
            parsed_href = urlparse(full_url)
            path = parsed_href.path
            if re.match(link_pattern, path):
                seen.add(clean)
                event_urls.append(clean)

        self.logger.info(f"follow_links: found {len(event_urls)} event page links")
        event_urls = event_urls[:max_pages]

        # Fetch each sub-page and extract events
        all_events = []
        for i, event_url in enumerate(event_urls):
            if i > 0:
                time.sleep(fetch_delay)
            try:
                resp = requests.get(event_url, headers=self.HEADERS, timeout=30)
                resp.raise_for_status()
                sub_html = resp.text

                if sub_strategy == "json_ld":
                    events = self._parse_json_ld(sub_html)
                elif sub_strategy == "ics":
                    events = self._parse_ics(sub_html)
                else:
                    events = self._parse_json_ld(sub_html)

                # Set ticket_url to the sub-page URL if not already set
                for ev in events:
                    if not ev.get("ticket_url"):
                        ev["ticket_url"] = event_url

                all_events.extend(events)
            except Exception as e:
                self.logger.warning(f"follow_links: failed to fetch {event_url}: {e}")
                continue

        self.logger.info(f"follow_links: extracted {len(all_events)} events from {len(event_urls)} pages")
        return all_events
