"""Orchestrates all source adapters: fetch, parse, deduplicate, store."""
import importlib
import json
import logging
import os
import time
from datetime import datetime

import yaml
from rapidfuzz import fuzz

from db.models import Source, Event, EventEntity, init_db
from ingestion.base import BaseAdapter

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")


def load_sources_config() -> list[dict]:
    path = os.path.join(CONFIG_DIR, "sources.yaml")
    with open(path) as f:
        return yaml.safe_load(f)["sources"]


def load_venues_config() -> dict:
    path = os.path.join(CONFIG_DIR, "venues.yaml")
    with open(path) as f:
        return yaml.safe_load(f).get("venues", {})


def get_adapter(source_cfg: dict) -> BaseAdapter:
    """Dynamically load and instantiate the adapter for a source."""
    module_path = source_cfg["parser_module"]
    mod = importlib.import_module(module_path)
    # Convention: each module has an `Adapter` class
    return mod.Adapter(source_cfg)


def ensure_source_record(source_cfg: dict) -> Source:
    """Get or create the Source row."""
    src, _ = Source.get_or_create(
        name=source_cfg["name"],
        defaults={
            "type": source_cfg.get("method", "scrape"),
            "url": source_cfg["url"],
            "method": source_cfg.get("method", "requests"),
            "active": source_cfg.get("enabled", True),
        },
    )
    return src


def store_events(source: Source, events: list[dict], raw_payload=None):
    """Upsert events into the database."""
    now = datetime.utcnow()
    stored = 0
    for ev in events:
        raw_hash = BaseAdapter.hash_event(ev)
        try:
            existing = Event.get(
                Event.source == source,
                Event.source_event_id == ev["source_event_id"],
            )
            # Update if content changed
            if existing.raw_hash != raw_hash:
                existing.title = ev["title"]
                existing.description = ev.get("description", "")
                existing.start_dt = ev["start_dt"]
                existing.end_dt = ev.get("end_dt")
                existing.venue_name = ev["venue_name"]
                existing.address = ev.get("address", "")
                existing.price_min = ev.get("price_min")
                existing.price_max = ev.get("price_max")
                existing.ticket_url = ev.get("ticket_url", "")
                existing.category = ev.get("category", "")
                existing.raw_hash = raw_hash
                existing.raw_json = json.dumps(ev.get("raw_json", {}), default=str)
                existing.last_seen_dt = now
                existing.status = "active"
                existing.save()
            else:
                existing.last_seen_dt = now
                existing.save()
        except Event.DoesNotExist:
            Event.create(
                source=source,
                source_event_id=ev["source_event_id"],
                title=ev["title"],
                description=ev.get("description", ""),
                start_dt=ev["start_dt"],
                end_dt=ev.get("end_dt"),
                venue_name=ev["venue_name"],
                address=ev.get("address", ""),
                neighborhood=ev.get("neighborhood", ""),
                price_min=ev.get("price_min"),
                price_max=ev.get("price_max"),
                ticket_url=ev.get("ticket_url", ""),
                category=ev.get("category", ""),
                raw_hash=raw_hash,
                raw_json=json.dumps(ev.get("raw_json", {}), default=str),
                first_seen_dt=now,
                last_seen_dt=now,
            )
            stored += 1

        # Store entities (artists, genres, etc.)
        for entity in ev.get("entities", []):
            EventEntity.get_or_create(
                event=Event.get(
                    Event.source == source,
                    Event.source_event_id == ev["source_event_id"],
                ),
                entity_type=entity["type"],
                entity_value=entity["value"],
            )

    return stored


def normalize_title(title: str) -> str:
    """Normalize title for dedup comparison."""
    import re
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def deduplicate_events():
    """Find and merge duplicate events across sources."""
    from datetime import timedelta

    events = list(Event.select().where(Event.status == "active").order_by(Event.start_dt))
    merged = 0

    for i, ev1 in enumerate(events):
        if ev1.status != "active":
            continue
        for ev2 in events[i + 1:]:
            if ev2.status != "active":
                continue
            # Must be within 2 hours
            try:
                dt_diff = abs((ev1.start_dt - ev2.start_dt).total_seconds())
            except TypeError:
                continue
            if dt_diff > 7200:
                continue

            # Check venue match
            venue_score = fuzz.ratio(
                ev1.venue_name.lower(), ev2.venue_name.lower()
            )
            if venue_score < 85:
                continue

            # Check title match
            t1 = normalize_title(ev1.title)
            t2 = normalize_title(ev2.title)
            title_score = fuzz.ratio(t1, t2)
            if title_score < 80:
                continue

            # Merge: keep the first-seen event, mark the other as stale
            if ev1.first_seen_dt <= ev2.first_seen_dt:
                keeper, dupe = ev1, ev2
            else:
                keeper, dupe = ev2, ev1

            # Merge ticket URL if keeper doesn't have one
            if not keeper.ticket_url and dupe.ticket_url:
                keeper.ticket_url = dupe.ticket_url
                keeper.save()

            dupe.status = "stale"
            dupe.save()
            merged += 1

    logger.info(f"Dedup: merged {merged} duplicate events")
    return merged


def enrich_events(venues_config: dict):
    """Enrich events with venue metadata from venues.yaml."""
    events = Event.select().where(Event.status == "active")
    enriched = 0
    for ev in events:
        for venue_name, info in venues_config.items():
            if fuzz.ratio(ev.venue_name.lower(), venue_name.lower()) > 85:
                ev.neighborhood = info.get("neighborhood", "")
                if info.get("lat"):
                    ev.lat = info["lat"]
                if info.get("lon"):
                    ev.lon = info["lon"]
                ev.save()
                enriched += 1
                break
    logger.info(f"Enriched {enriched} events with venue metadata")
    return enriched


def run_ingestion(source_filter: str = None):
    """Main ingestion entry point."""
    init_db()
    sources_config = load_sources_config()
    venues_config = load_venues_config()

    stats = {"success": 0, "failed": 0, "events_stored": 0}

    for src_cfg in sources_config:
        if not src_cfg.get("enabled", True):
            continue
        if source_filter and src_cfg["name"] != source_filter:
            continue

        source = ensure_source_record(src_cfg)
        adapter = get_adapter(src_cfg)

        retries = 3
        for attempt in range(1, retries + 1):
            try:
                events, raw = adapter.run()
                stored = store_events(source, events, raw)
                stats["success"] += 1
                stats["events_stored"] += stored
                logger.info(f"{src_cfg['name']}: stored {stored} new, {len(events)} total parsed")
                break
            except Exception as e:
                logger.error(f"{src_cfg['name']} attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
                else:
                    stats["failed"] += 1

    # Post-processing
    deduplicate_events()
    enrich_events(venues_config)

    logger.info(f"Ingestion complete: {stats}")
    return stats
