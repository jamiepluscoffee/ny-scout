"""Base adapter interface for all event sources."""
from __future__ import annotations

import abc
import hashlib
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class EventDict(dict):
    """Thin wrapper for validated event data before DB insertion."""

    REQUIRED_KEYS = {"source_event_id", "title", "start_dt", "venue_name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        missing = self.REQUIRED_KEYS - set(self.keys())
        if missing:
            raise ValueError(f"EventDict missing required keys: {missing}")


class BaseAdapter(abc.ABC):
    """Abstract base class for all source adapters."""

    def __init__(self, source_config: dict):
        self.config = source_config
        self.name = source_config["name"]
        self.url = source_config["url"]
        self.logger = logging.getLogger(f"adapter.{self.name}")

    @abc.abstractmethod
    def fetch_raw(self) -> Any:
        """Fetch raw data from the source. Returns raw payload (str, bytes, dict)."""

    @abc.abstractmethod
    def parse(self, raw: Any) -> list[EventDict]:
        """Parse raw payload into a list of EventDicts."""

    def run(self) -> tuple[list[EventDict], Any]:
        """Execute fetch + parse, returning (events, raw_payload)."""
        self.logger.info(f"Fetching from {self.name}...")
        raw = self.fetch_raw()
        self.logger.info(f"Parsing {self.name}...")
        events = self.parse(raw)
        self.logger.info(f"{self.name}: parsed {len(events)} events")
        return events, raw

    @staticmethod
    def hash_event(event_dict: dict) -> str:
        """Create a content hash for change detection."""
        content = json.dumps(
            {k: str(v) for k, v in sorted(event_dict.items()) if k != "raw_json"},
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def make_event_id(source_name: str, unique_part: str) -> str:
        """Generate a deterministic source_event_id."""
        return f"{source_name}:{unique_part}"

    @staticmethod
    def parse_datetime(dt_str: str, fmt: str = None) -> datetime | None:
        """Try to parse a datetime string with common formats."""
        if isinstance(dt_str, datetime):
            return dt_str
        if not dt_str:
            return None
        formats = [fmt] if fmt else [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %I:%M %p",
            "%B %d, %Y %I:%M %p",
            "%b %d, %Y",
        ]
        for f in formats:
            try:
                return datetime.strptime(dt_str.strip(), f)
            except (ValueError, AttributeError):
                continue
        return None
