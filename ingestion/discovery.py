"""Source Discovery — process shared links to find new event sources.

Given a URL, this module:
1. Fetches the page and classifies it (event page, calendar, or unknown)
2. Extracts any event data it can find
3. Discovers the parent venue/org and looks for a calendar source
4. Registers new sources in sources.yaml for automatic future ingestion
5. Updates taste signals (venue boost, artist affinity) from shared links
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from ingestion.base import BaseAdapter, EventDict

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

FETCH_DELAY = 2  # seconds between fetches, to be polite


# ---------------------------------------------------------------------------
# Link file I/O
# ---------------------------------------------------------------------------

def load_discovered_links() -> list[dict]:
    path = os.path.join(CONFIG_DIR, "discovered_links.yaml")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("links", []) or []


def save_discovered_links(links: list[dict]):
    path = os.path.join(CONFIG_DIR, "discovered_links.yaml")
    with open(path) as f:
        content = f.read()

    # Preserve the header comments
    header_lines = []
    for line in content.split("\n"):
        if line.startswith("#") or line.strip() == "":
            header_lines.append(line)
        else:
            break
    header = "\n".join(header_lines)

    data = {"links": links}
    body = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    with open(path, "w") as f:
        f.write(header + "\n" + body)


def add_link(url: str, note: str = "") -> dict:
    """Add a new link to discovered_links.yaml."""
    links = load_discovered_links()
    # Check for duplicate
    for link in links:
        if link.get("url") == url:
            logger.info(f"Link already exists: {url}")
            return link

    entry = {
        "url": url,
        "added": datetime.utcnow().strftime("%Y-%m-%d"),
    }
    if note:
        entry["note"] = note

    links.append(entry)
    save_discovered_links(links)
    logger.info(f"Added link: {url}")
    return entry


# ---------------------------------------------------------------------------
# Page fetching & classification
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> tuple[str, requests.Response]:
    """Fetch a URL and return (html, response)."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text, resp


def classify_page(url: str, html: str) -> dict:
    """Classify a page as 'event', 'calendar', or 'unknown'.

    Returns dict with:
      - type: 'event' | 'calendar' | 'unknown'
      - json_ld: list of Schema.org items found
      - has_ics: bool, whether an ICS feed link was found
      - ics_url: str, the ICS feed URL if found
      - event_links: list of event-like links found on the page
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "type": "unknown",
        "json_ld": [],
        "has_ics": False,
        "ics_url": None,
        "event_links": [],
        "venue_name": None,
    }

    # 1. Check for JSON-LD
    event_types = {"Event", "MusicEvent", "TheaterEvent",
                   "DanceEvent", "ExhibitionEvent", "SocialEvent"}
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") in event_types:
                result["json_ld"].append(item)

    # 2. Check for ICS feed
    for link in soup.find_all(["a", "link"], href=True):
        href = link.get("href", "")
        if href.endswith(".ics") or "ical" in href.lower() or "webcal" in href.lower():
            result["has_ics"] = True
            result["ics_url"] = urljoin(url, href)
            break

    # 3. Look for event-like links (for calendar pages)
    # Derive a link pattern from the listing page URL itself:
    # if we're on /shows, look for /shows/something links
    parsed_url = urlparse(url)
    listing_path = parsed_url.path.rstrip("/")
    listing_host = parsed_url.netloc
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(url, href)
        parsed_href = urlparse(full_url)
        href_path = parsed_href.path
        # Skip external links, ICS/ical links, and query-only variants
        if parsed_href.netloc and parsed_href.netloc != listing_host:
            continue
        if "format=ical" in full_url or href_path.endswith(".ics"):
            continue
        # Match links that are children of the listing path (same domain)
        if listing_path and href_path.startswith(listing_path + "/") and href_path != listing_path + "/":
            clean = full_url.split("?")[0].split("#")[0]
            if clean not in result["event_links"]:
                result["event_links"].append(clean)
        # Also match general event-like path patterns
        elif re.search(r"/(events?|shows?|performances?|concerts?|tickets?|calendar)/[^/]+", href, re.I):
            clean = full_url.split("?")[0].split("#")[0]
            if clean not in result["event_links"]:
                result["event_links"].append(clean)

    # 4. Try to extract venue name from the page
    # Check og:site_name, then <title>
    og_site = soup.find("meta", property="og:site_name")
    if og_site:
        result["venue_name"] = og_site.get("content", "").strip()
    elif soup.title:
        # Use domain-derived name as fallback
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        result["venue_name"] = domain.split(".")[0].replace("-", " ").title()

    # 5. Classify
    if len(result["json_ld"]) == 1 and not result["event_links"]:
        result["type"] = "event"
    elif len(result["json_ld"]) > 1 or result["event_links"] or result["has_ics"]:
        result["type"] = "calendar"
    elif len(result["json_ld"]) == 1:
        result["type"] = "event"
    else:
        # Check URL patterns
        parsed = urlparse(url)
        path = parsed.path.lower()
        if re.search(r"/(calendar|events|schedule|shows|tickets|lineup)", path):
            result["type"] = "calendar"
        elif re.search(r"/(event|show|performance|ticket)/[^/]+", path):
            result["type"] = "event"

    return result


# ---------------------------------------------------------------------------
# Event extraction from a single page
# ---------------------------------------------------------------------------

def extract_events_from_page(url: str, html: str, classification: dict,
                             source_name: str) -> list[EventDict]:
    """Extract event data from a page using the best available method."""
    events = []

    # JSON-LD extraction (highest confidence)
    for item in classification["json_ld"]:
        event = _jsonld_to_event(item, source_name)
        if event:
            events.append(event)

    if events:
        return events

    # OpenGraph fallback for single event pages
    if classification["type"] == "event":
        event = _opengraph_to_event(html, url, source_name)
        if event:
            events.append(event)

    return events


def _jsonld_to_event(item: dict, source_name: str) -> EventDict | None:
    """Convert a JSON-LD Schema.org event to an EventDict."""
    title = item.get("name", "").strip()
    start_str = item.get("startDate", "")
    start_dt = BaseAdapter.parse_datetime(start_str)
    if not title or not start_dt:
        return None

    end_dt = BaseAdapter.parse_datetime(item.get("endDate", ""))

    location = item.get("location", {})
    if isinstance(location, dict):
        venue_name = location.get("name", "Unknown Venue")
        address_obj = location.get("address", {})
        address = (address_obj.get("streetAddress", "")
                   if isinstance(address_obj, dict) else str(address_obj))
    else:
        venue_name = str(location) if location else "Unknown Venue"
        address = ""

    # Performers
    entities = []
    performers = item.get("performer", [])
    if not isinstance(performers, list):
        performers = [performers]
    for perf in performers:
        if isinstance(perf, dict) and perf.get("name"):
            entities.append({"type": "artist", "value": perf["name"]})
        elif isinstance(perf, str) and perf:
            entities.append({"type": "artist", "value": perf})

    # Price
    offers = item.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price_min = offers.get("price") or offers.get("lowPrice")
    price_max = offers.get("highPrice")

    ticket_url = item.get("url", "")

    # Category from @type
    type_to_cat = {
        "MusicEvent": "concert", "TheaterEvent": "theatre",
        "ExhibitionEvent": "exhibition",
    }
    category = type_to_cat.get(item.get("@type", ""), "")

    event_id = BaseAdapter.make_event_id(
        source_name, f"{venue_name}:{start_str}:{title[:30]}"
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


def _opengraph_to_event(html: str, url: str, source_name: str) -> EventDict | None:
    """Try to extract an event from OpenGraph meta tags."""
    soup = BeautifulSoup(html, "html.parser")

    def og(prop):
        tag = soup.find("meta", property=f"og:{prop}")
        return tag.get("content", "").strip() if tag else ""

    title = og("title")
    if not title:
        title = soup.title.get_text(strip=True) if soup.title else ""
    if not title:
        return None

    # Try to find a date — look for meta tags, time elements, or date patterns
    start_dt = None
    # Check for event:start_time (used by Facebook events, some sites)
    start_meta = soup.find("meta", property="event:start_time")
    if start_meta:
        start_dt = BaseAdapter.parse_datetime(start_meta.get("content", ""))

    # Check <time> elements
    if not start_dt:
        time_el = soup.find("time", datetime=True)
        if time_el:
            start_dt = BaseAdapter.parse_datetime(time_el["datetime"])

    if not start_dt:
        return None

    venue_name = og("site_name") or "Unknown Venue"
    description = og("description")

    event_id = BaseAdapter.make_event_id(
        source_name, f"{venue_name}:{start_dt.isoformat()}:{title[:30]}"
    )

    return EventDict(
        source_event_id=event_id,
        title=title,
        description=description,
        start_dt=start_dt,
        venue_name=venue_name,
        ticket_url=url,
        category="",
    )


# ---------------------------------------------------------------------------
# Source discovery & registration
# ---------------------------------------------------------------------------

def derive_calendar_url(url: str, html: str) -> str | None:
    """From a single event URL, try to find the venue's calendar page."""
    parsed = urlparse(url)
    soup = BeautifulSoup(html, "html.parser")

    # 1. Look for explicit calendar/events links
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(strip=True).lower()
        if any(kw in href or kw in text for kw in
               ["calendar", "events", "schedule", "shows", "tickets", "lineup", "upcoming"]):
            return urljoin(url, a["href"])

    # 2. Try common calendar paths on the same domain
    common_paths = ["/events", "/calendar", "/shows", "/schedule", "/tickets"]
    base = f"{parsed.scheme}://{parsed.netloc}"
    for path in common_paths:
        candidate = base + path
        if candidate != url:
            return candidate

    return None


def probe_source(url: str) -> dict | None:
    """Check if a URL is a viable event source. Returns extraction config or None."""
    try:
        html, _ = fetch_page(url)
    except Exception as e:
        logger.warning(f"Failed to probe {url}: {e}")
        return None

    classification = classify_page(url, html)

    # Must have some events or be identifiable as a calendar
    if classification["type"] == "unknown" and not classification["json_ld"]:
        return None

    # Determine best extraction strategy
    if classification["json_ld"]:
        return {
            "strategy": "json_ld",
            "event_count": len(classification["json_ld"]),
            "venue_name": classification.get("venue_name"),
        }
    elif classification["has_ics"] and not classification["event_links"]:
        return {
            "strategy": "ics",
            "ics_url": classification["ics_url"],
            "venue_name": classification.get("venue_name"),
        }
    elif classification["event_links"]:
        # Listing page with links to individual event pages.
        # Probe the first event link to confirm sub-pages have extractable data.
        first_link = classification["event_links"][0]
        try:
            sub_html, _ = fetch_page(first_link)
            sub_class = classify_page(first_link, sub_html)
            if sub_class["json_ld"]:
                sub_strategy = "json_ld"
            elif sub_class["has_ics"]:
                sub_strategy = "ics"
            else:
                logger.info(f"follow_links: sub-page {first_link} has no extractable data")
                return None
            return {
                "strategy": "follow_links",
                "sub_strategy": sub_strategy,
                "event_link_count": len(classification["event_links"]),
                "venue_name": classification.get("venue_name"),
            }
        except Exception as e:
            logger.warning(f"follow_links: failed to probe sub-page {first_link}: {e}")
            return None

    return None


def source_name_from_url(url: str) -> str:
    """Generate a source name from a URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    name = domain.split(".")[0]
    # Clean up: lowercase, underscores
    name = re.sub(r"[^a-z0-9]", "_", name.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def load_sources_config() -> list[dict]:
    path = os.path.join(CONFIG_DIR, "sources.yaml")
    with open(path) as f:
        return yaml.safe_load(f)["sources"]


def save_sources_config(sources: list[dict]):
    path = os.path.join(CONFIG_DIR, "sources.yaml")
    with open(path, "w") as f:
        yaml.dump({"sources": sources}, f, default_flow_style=False,
                  sort_keys=False, allow_unicode=True)


def register_source(url: str, name: str, extraction_config: dict,
                     category: str = "") -> dict | None:
    """Register a new source in sources.yaml. Returns the new config entry or None."""
    sources = load_sources_config()

    # Check if already registered
    for src in sources:
        if src["name"] == name or src["url"] == url:
            logger.info(f"Source already registered: {name} ({url})")
            return None

    venue_name = extraction_config.pop("venue_name", None)
    extraction_config.pop("event_count", None)

    new_source = {
        "name": name,
        "url": url,
        "category": category,
        "method": "discovered",
        "parser_module": "ingestion.sources.generic",
        "cadence": "daily",
        "enabled": True,
        "origin": "discovered",
        "discovered_from": url,
        "extraction": extraction_config,
    }
    if venue_name:
        new_source["extraction"]["default_venue"] = venue_name

    sources.append(new_source)
    save_sources_config(sources)
    logger.info(f"Registered new source: {name} ({url}) strategy={extraction_config.get('strategy')}")
    return new_source


# ---------------------------------------------------------------------------
# Taste signal updates
# ---------------------------------------------------------------------------

def update_taste_signals(events: list[EventDict], url: str):
    """Update taste profile and preferences based on discovered events."""
    if not events:
        return

    # Collect artist names and venue names
    artists = set()
    venues = set()
    for ev in events:
        if ev.get("venue_name") and ev["venue_name"] != "Unknown Venue":
            venues.add(ev["venue_name"])
        for entity in ev.get("entities", []):
            if entity["type"] == "artist" and entity["value"]:
                artists.add(entity["value"])

    # Update venue boosts in preferences.yaml
    if venues:
        _update_venue_boosts(venues)

    # Update artist affinities in taste_profile.yaml
    if artists:
        _update_artist_affinities(artists)


def _update_venue_boosts(venues: set):
    """Add new venues to preferences.yaml with a default boost."""
    path = os.path.join(CONFIG_DIR, "preferences.yaml")
    with open(path) as f:
        prefs = yaml.safe_load(f) or {}

    existing = prefs.get("venue_boost", {})
    added = []
    for venue in venues:
        # Check if already present (fuzzy would be nice, but exact is safe)
        if venue not in existing:
            existing[venue] = 5  # Default: moderate interest
            added.append(venue)

    if added:
        prefs["venue_boost"] = existing
        with open(path, "w") as f:
            yaml.dump(prefs, f, default_flow_style=False, sort_keys=False,
                      allow_unicode=True)
        logger.info(f"Added venue boosts: {added}")


def _update_artist_affinities(artists: set):
    """Add new artists to taste_profile.yaml with a default affinity."""
    path = os.path.join(CONFIG_DIR, "taste_profile.yaml")
    with open(path) as f:
        content = f.read()

    data = yaml.safe_load(content) or {}
    existing = data.get("artist_affinities", {})
    if existing is None:
        existing = {}

    added = []
    for artist in artists:
        if artist not in existing:
            existing[artist] = 0.6  # Default: moderate affinity
            added.append(artist)

    if added:
        data["artist_affinities"] = existing
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False,
                      allow_unicode=True)
        logger.info(f"Added artist affinities: {added}")


# ---------------------------------------------------------------------------
# Main discovery flow
# ---------------------------------------------------------------------------

def process_link(link: dict) -> dict:
    """Process a single discovered link. Returns updated link dict with status.

    Possible statuses:
      - processed: successfully handled
      - failed: error during processing
      - unclear: could not classify, needs Jamie's input
    """
    url = link["url"]
    logger.info(f"Processing link: {url}")

    try:
        html, resp = fetch_page(url)
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        link["status"] = "failed"
        link["status_note"] = f"Fetch failed: {e}"
        return link

    classification = classify_page(url, html)
    link["classified_as"] = classification["type"]
    logger.info(f"Classified as: {classification['type']}")

    if classification["type"] == "unknown":
        link["status"] = "unclear"
        link["status_note"] = "Could not determine page type — please clarify what this link is for"
        logger.warning(f"Unknown page type for {url} — marked as unclear")
        return link

    # Extract events from this page
    source_name = source_name_from_url(url)
    events = extract_events_from_page(url, html, classification, source_name)
    link["events_found"] = len(events)
    logger.info(f"Extracted {len(events)} events from page")

    # Update taste signals from what we found
    update_taste_signals(events, url)

    # Try to discover & register a recurring source
    source_registered = False
    if classification["type"] == "calendar":
        # This page IS a calendar — register it directly
        probe_result = probe_source(url)
        if probe_result:
            registered = register_source(url, source_name, probe_result,
                                         category=link.get("category", ""))
            if registered:
                source_registered = True
                link["source_registered"] = source_name
    elif classification["type"] == "event":
        # Single event — try to find the venue's calendar
        calendar_url = derive_calendar_url(url, html)
        if calendar_url:
            time.sleep(FETCH_DELAY)
            probe_result = probe_source(calendar_url)
            if probe_result:
                cal_source_name = source_name_from_url(calendar_url)
                registered = register_source(calendar_url, cal_source_name,
                                             probe_result,
                                             category=link.get("category", ""))
                if registered:
                    source_registered = True
                    link["source_registered"] = cal_source_name
                    link["calendar_url"] = calendar_url

    link["status"] = "processed"
    summary = f"{len(events)} events extracted"
    if source_registered:
        summary += f", source '{link['source_registered']}' registered"
    link["status_note"] = summary
    return link


def run_discovery() -> dict:
    """Process all pending links. Returns summary stats."""
    links = load_discovered_links()
    pending = [l for l in links if not l.get("status")]

    if not pending:
        logger.info("No pending links to process")
        return {"processed": 0, "sources_registered": 0, "events_found": 0, "unclear": 0}

    stats = {"processed": 0, "sources_registered": 0, "events_found": 0,
             "failed": 0, "unclear": 0}

    for i, link in enumerate(pending):
        if i > 0:
            time.sleep(FETCH_DELAY)

        process_link(link)

        if link.get("status") == "processed":
            stats["processed"] += 1
            stats["events_found"] += link.get("events_found", 0)
            if link.get("source_registered"):
                stats["sources_registered"] += 1
        elif link.get("status") == "unclear":
            stats["unclear"] += 1
        else:
            stats["failed"] += 1

    # Save updated links with status
    save_discovered_links(links)

    logger.info(f"Discovery complete: {stats}")
    return stats
