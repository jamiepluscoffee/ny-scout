"""Tests for source discovery: classification, extraction, and registration."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

import yaml
import pytest

from ingestion.discovery import (
    classify_page,
    extract_events_from_page,
    source_name_from_url,
    probe_source,
    register_source,
    add_link,
    load_discovered_links,
    save_discovered_links,
    process_link,
    _jsonld_to_event,
    _opengraph_to_event,
    derive_calendar_url,
    update_taste_signals,
)
from ingestion.base import EventDict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SINGLE_EVENT_JSONLD = json.dumps({
    "@type": "MusicEvent",
    "name": "Brad Mehldau Trio",
    "startDate": "2026-03-15T20:00:00",
    "endDate": "2026-03-15T22:00:00",
    "location": {
        "@type": "Place",
        "name": "Village Vanguard",
        "address": {"streetAddress": "178 7th Ave S"}
    },
    "performer": [{"@type": "Person", "name": "Brad Mehldau"}],
    "offers": {"price": "35", "highPrice": "45"},
    "url": "https://villagevanguard.com/events/mehldau"
})

MULTI_EVENT_JSONLD = json.dumps([
    {
        "@type": "MusicEvent",
        "name": "Joel Ross Good Vibes",
        "startDate": "2026-03-16T21:00:00",
        "location": {"name": "The Jazz Gallery"},
    },
    {
        "@type": "MusicEvent",
        "name": "Ambrose Akinmusire Quartet",
        "startDate": "2026-03-17T20:00:00",
        "location": {"name": "The Jazz Gallery"},
    },
])


def make_html(json_ld=None, title="Test Page", ics_link=None, event_links=None,
              og_title=None, og_site=None, calendar_link=None, time_el=None):
    """Build a simple HTML page for testing."""
    parts = [f"<html><head><title>{title}</title>"]
    if og_title:
        parts.append(f'<meta property="og:title" content="{og_title}">')
    if og_site:
        parts.append(f'<meta property="og:site_name" content="{og_site}">')
    if json_ld:
        parts.append(f'<script type="application/ld+json">{json_ld}</script>')
    if ics_link:
        parts.append(f'<link rel="alternate" type="text/calendar" href="{ics_link}">')
    parts.append("</head><body>")
    if calendar_link:
        parts.append(f'<a href="{calendar_link}">View Calendar</a>')
    if time_el:
        parts.append(f'<time datetime="{time_el}">Event Date</time>')
    for link in (event_links or []):
        parts.append(f'<a href="{link}">Event</a>')
    parts.append("</body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

class TestClassifyPage:
    def test_single_event_jsonld(self):
        html = make_html(json_ld=SINGLE_EVENT_JSONLD)
        result = classify_page("https://example.com/event/123", html)
        assert result["type"] == "event"
        assert len(result["json_ld"]) == 1

    def test_multi_event_jsonld_is_calendar(self):
        html = make_html(json_ld=MULTI_EVENT_JSONLD)
        result = classify_page("https://example.com/events", html)
        assert result["type"] == "calendar"
        assert len(result["json_ld"]) == 2

    def test_ics_link_is_calendar(self):
        html = make_html(ics_link="/feed/calendar.ics")
        result = classify_page("https://example.com/events", html)
        assert result["type"] == "calendar"
        assert result["has_ics"] is True
        assert result["ics_url"] == "https://example.com/feed/calendar.ics"

    def test_event_links_make_calendar(self):
        html = make_html(event_links=["/event/1", "/event/2", "/event/3"])
        result = classify_page("https://example.com/calendar", html)
        assert result["type"] == "calendar"

    def test_calendar_url_pattern(self):
        html = make_html()
        result = classify_page("https://example.com/events", html)
        assert result["type"] == "calendar"

    def test_unknown_page(self):
        html = make_html(title="About Us")
        result = classify_page("https://example.com/about", html)
        assert result["type"] == "unknown"

    def test_og_site_name_extracted(self):
        html = make_html(og_site="Barbès")
        result = classify_page("https://barbesbrooklyn.com/events", html)
        assert result["venue_name"] == "Barbès"

    def test_non_event_jsonld_ignored(self):
        non_event = json.dumps({"@type": "Organization", "name": "Foo"})
        html = make_html(json_ld=non_event)
        result = classify_page("https://example.com/about", html)
        assert len(result["json_ld"]) == 0


# ---------------------------------------------------------------------------
# Extraction tests
# ---------------------------------------------------------------------------

class TestJsonLdExtraction:
    def test_full_event_extraction(self):
        event = _jsonld_to_event(json.loads(SINGLE_EVENT_JSONLD), "test_source")
        assert event is not None
        assert event["title"] == "Brad Mehldau Trio"
        assert event["venue_name"] == "Village Vanguard"
        assert event["price_min"] == 35.0
        assert event["price_max"] == 45.0
        assert event["ticket_url"] == "https://villagevanguard.com/events/mehldau"
        assert any(e["value"] == "Brad Mehldau" for e in event["entities"])

    def test_missing_title_returns_none(self):
        item = {"@type": "MusicEvent", "startDate": "2026-03-15T20:00:00"}
        assert _jsonld_to_event(item, "test") is None

    def test_missing_date_returns_none(self):
        item = {"@type": "MusicEvent", "name": "Some Event"}
        assert _jsonld_to_event(item, "test") is None

    def test_category_from_type(self):
        item = json.loads(SINGLE_EVENT_JSONLD)
        event = _jsonld_to_event(item, "test")
        assert event["category"] == "concert"

        item["@type"] = "TheaterEvent"
        event = _jsonld_to_event(item, "test")
        assert event["category"] == "theatre"

    def test_string_location(self):
        item = {
            "@type": "MusicEvent",
            "name": "Show",
            "startDate": "2026-03-15T20:00:00",
            "location": "Some Place",
        }
        event = _jsonld_to_event(item, "test")
        assert event["venue_name"] == "Some Place"

    def test_multiple_performers(self):
        item = json.loads(SINGLE_EVENT_JSONLD)
        item["performer"] = [
            {"@type": "Person", "name": "Brad Mehldau"},
            {"@type": "Person", "name": "Larry Grenadier"},
        ]
        event = _jsonld_to_event(item, "test")
        artists = [e["value"] for e in event["entities"]]
        assert "Brad Mehldau" in artists
        assert "Larry Grenadier" in artists


class TestOpenGraphExtraction:
    def test_og_with_time_element(self):
        html = make_html(
            og_title="Brad Mehldau at Village Vanguard",
            og_site="Village Vanguard",
            time_el="2026-03-15T20:00:00",
        )
        event = _opengraph_to_event(html, "https://example.com/event/1", "test")
        assert event is not None
        assert event["title"] == "Brad Mehldau at Village Vanguard"
        assert event["venue_name"] == "Village Vanguard"

    def test_og_without_date_returns_none(self):
        html = make_html(og_title="Some Event", og_site="Some Venue")
        event = _opengraph_to_event(html, "https://example.com/event/1", "test")
        assert event is None


class TestExtractEventsFromPage:
    def test_prefers_jsonld(self):
        html = make_html(json_ld=SINGLE_EVENT_JSONLD, og_title="Fallback Title",
                         time_el="2026-03-15T20:00:00")
        classification = classify_page("https://example.com/event/1", html)
        events = extract_events_from_page(
            "https://example.com/event/1", html, classification, "test")
        assert len(events) == 1
        assert events[0]["title"] == "Brad Mehldau Trio"  # From JSON-LD, not OG

    def test_falls_back_to_og(self):
        html = make_html(og_title="Jazz Night", og_site="Cool Venue",
                         time_el="2026-03-20T19:00:00")
        classification = classify_page("https://example.com/event/1", html)
        classification["type"] = "event"  # Force event type
        events = extract_events_from_page(
            "https://example.com/event/1", html, classification, "test")
        assert len(events) == 1
        assert events[0]["title"] == "Jazz Night"


# ---------------------------------------------------------------------------
# Source name derivation
# ---------------------------------------------------------------------------

class TestSourceNameFromUrl:
    def test_simple_domain(self):
        assert source_name_from_url("https://barbesbrooklyn.com/events") == "barbesbrooklyn"

    def test_www_stripped(self):
        assert source_name_from_url("https://www.example.com/calendar") == "example"

    def test_hyphens_to_underscores(self):
        assert source_name_from_url("https://le-poisson-rouge.com") == "le_poisson_rouge"


# ---------------------------------------------------------------------------
# Calendar URL derivation
# ---------------------------------------------------------------------------

class TestDeriveCalendarUrl:
    def test_finds_calendar_link(self):
        html = make_html(calendar_link="/calendar")
        url = derive_calendar_url("https://example.com/event/123", html)
        assert url == "https://example.com/calendar"

    def test_no_calendar_link_tries_common_paths(self):
        html = make_html()
        url = derive_calendar_url("https://example.com/event/123", html)
        assert url is not None
        assert "/events" in url or "/calendar" in url


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------

class TestRegisterSource:
    def setup_method(self):
        """Set up a temp config dir."""
        self.tmpdir = tempfile.mkdtemp()
        self.orig_config_dir = os.environ.get("CONFIG_DIR")

        # Write a minimal sources.yaml
        sources_path = os.path.join(self.tmpdir, "sources.yaml")
        with open(sources_path, "w") as f:
            yaml.dump({"sources": [
                {"name": "existing", "url": "https://existing.com", "enabled": True}
            ]}, f)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    @patch("ingestion.discovery.CONFIG_DIR")
    def test_registers_new_source(self, mock_dir):
        mock_dir.__str__ = lambda _: self.tmpdir
        # Patch at module level
        import ingestion.discovery as disc
        orig = disc.CONFIG_DIR
        disc.CONFIG_DIR = self.tmpdir
        try:
            result = register_source(
                "https://newvenue.com/events", "newvenue",
                {"strategy": "json_ld", "venue_name": "New Venue"},
                category="jazz"
            )
            assert result is not None
            assert result["name"] == "newvenue"
            assert result["parser_module"] == "ingestion.sources.generic"
            assert result["origin"] == "discovered"

            # Verify it was written
            sources = disc.load_sources_config()
            names = [s["name"] for s in sources]
            assert "newvenue" in names
        finally:
            disc.CONFIG_DIR = orig

    @patch("ingestion.discovery.CONFIG_DIR")
    def test_skips_duplicate(self, mock_dir):
        import ingestion.discovery as disc
        orig = disc.CONFIG_DIR
        disc.CONFIG_DIR = self.tmpdir
        try:
            result = register_source(
                "https://existing.com", "existing",
                {"strategy": "json_ld"})
            assert result is None
        finally:
            disc.CONFIG_DIR = orig


# ---------------------------------------------------------------------------
# Taste signal updates
# ---------------------------------------------------------------------------

class TestTasteSignals:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        # Write minimal config files
        with open(os.path.join(self.tmpdir, "preferences.yaml"), "w") as f:
            yaml.dump({"venue_boost": {"Village Vanguard": 8}}, f)
        with open(os.path.join(self.tmpdir, "taste_profile.yaml"), "w") as f:
            yaml.dump({"artist_affinities": {}}, f)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_adds_venue_boost(self):
        import ingestion.discovery as disc
        orig = disc.CONFIG_DIR
        disc.CONFIG_DIR = self.tmpdir
        try:
            events = [EventDict(
                source_event_id="test:1",
                title="Show",
                start_dt="2026-03-15T20:00:00",
                venue_name="Barbès",
            )]
            update_taste_signals(events, "https://example.com")

            with open(os.path.join(self.tmpdir, "preferences.yaml")) as f:
                prefs = yaml.safe_load(f)
            assert "Barbès" in prefs["venue_boost"]
            assert prefs["venue_boost"]["Barbès"] == 5
            # Existing venue unchanged
            assert prefs["venue_boost"]["Village Vanguard"] == 8
        finally:
            disc.CONFIG_DIR = orig

    def test_adds_artist_affinity(self):
        import ingestion.discovery as disc
        orig = disc.CONFIG_DIR
        disc.CONFIG_DIR = self.tmpdir
        try:
            events = [EventDict(
                source_event_id="test:1",
                title="Show",
                start_dt="2026-03-15T20:00:00",
                venue_name="Some Venue",
                entities=[{"type": "artist", "value": "Joel Ross"}],
            )]
            update_taste_signals(events, "https://example.com")

            with open(os.path.join(self.tmpdir, "taste_profile.yaml")) as f:
                data = yaml.safe_load(f)
            assert "Joel Ross" in data["artist_affinities"]
            assert data["artist_affinities"]["Joel Ross"] == 0.6
        finally:
            disc.CONFIG_DIR = orig


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------

class TestLinkManagement:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        path = os.path.join(self.tmpdir, "discovered_links.yaml")
        with open(path, "w") as f:
            f.write("# Header comment\n\nlinks: []\n")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def test_add_link(self):
        import ingestion.discovery as disc
        orig = disc.CONFIG_DIR
        disc.CONFIG_DIR = self.tmpdir
        try:
            entry = add_link("https://example.com/event/1", note="test link")
            assert entry["url"] == "https://example.com/event/1"
            assert entry["note"] == "test link"

            links = load_discovered_links()
            assert len(links) == 1
        finally:
            disc.CONFIG_DIR = orig

    def test_add_duplicate_link(self):
        import ingestion.discovery as disc
        orig = disc.CONFIG_DIR
        disc.CONFIG_DIR = self.tmpdir
        try:
            add_link("https://example.com/event/1")
            add_link("https://example.com/event/1")  # duplicate

            links = load_discovered_links()
            assert len(links) == 1
        finally:
            disc.CONFIG_DIR = orig


# ---------------------------------------------------------------------------
# Follow links strategy
# ---------------------------------------------------------------------------

class TestFollowLinks:
    """Test the follow_links strategy in the generic adapter."""

    def _make_adapter(self, url="https://example.com/shows", **extraction_overrides):
        from ingestion.sources.generic import Adapter
        config = {
            "name": "test_follow",
            "url": url,
            "category": "concert",
            "extraction": {"strategy": "follow_links", **extraction_overrides},
        }
        return Adapter(config)

    def test_discovers_event_links_from_listing(self):
        """Listing page with sub-page links → adapter finds the links."""
        adapter = self._make_adapter()
        listing_html = make_html(
            event_links=["/shows/event-a", "/shows/event-b", "/shows/event-c"],
            title="All Shows"
        )

        # Build sub-page HTML with JSON-LD
        sub_page_html = make_html(json_ld=SINGLE_EVENT_JSONLD)

        with patch("ingestion.sources.generic.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = sub_page_html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            events = adapter._parse_follow_links(listing_html)

        assert len(events) == 3  # One event per sub-page
        assert events[0]["title"] == "Brad Mehldau Trio"

    def test_respects_max_pages(self):
        """Should stop after max_pages sub-pages."""
        adapter = self._make_adapter(max_pages=2)

        # 5 links but max_pages=2
        links = [f"/shows/event-{i}" for i in range(5)]
        listing_html = make_html(event_links=links)
        sub_page_html = make_html(json_ld=SINGLE_EVENT_JSONLD)

        with patch("ingestion.sources.generic.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = sub_page_html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            events = adapter._parse_follow_links(listing_html)

        assert len(events) == 2
        assert mock_get.call_count == 2

    def test_skips_failed_sub_pages(self):
        """Failed sub-page fetches should be skipped, not crash."""
        adapter = self._make_adapter()
        listing_html = make_html(
            event_links=["/shows/good", "/shows/bad", "/shows/also-good"]
        )
        sub_page_html = make_html(json_ld=SINGLE_EVENT_JSONLD)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 2:
                raise requests.exceptions.Timeout("timed out")
            mock_resp.text = sub_page_html
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with patch("ingestion.sources.generic.requests.get", side_effect=side_effect):
            events = adapter._parse_follow_links(listing_html)

        assert len(events) == 2  # 2 successful, 1 failed

    def test_deduplicates_links(self):
        """Same URL appearing multiple times should only be fetched once."""
        adapter = self._make_adapter()
        # Duplicate links in the HTML
        listing_html = (
            '<html><body>'
            '<a href="/shows/event-a">Link 1</a>'
            '<a href="/shows/event-a">Link 2</a>'  # duplicate
            '<a href="/shows/event-a?ref=nav">Link 3</a>'  # same path, query param
            '</body></html>'
        )
        sub_page_html = make_html(json_ld=SINGLE_EVENT_JSONLD)

        with patch("ingestion.sources.generic.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = sub_page_html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            events = adapter._parse_follow_links(listing_html)

        assert mock_get.call_count == 1  # Only one unique URL
        assert len(events) == 1

    def test_custom_link_pattern(self):
        """Custom link_pattern should filter which links are followed."""
        adapter = self._make_adapter(link_pattern=r"/concerts/\d+")
        listing_html = (
            '<html><body>'
            '<a href="/concerts/123">Concert</a>'
            '<a href="/concerts/456">Concert</a>'
            '<a href="/about">About</a>'
            '<a href="/shows/other">Other</a>'
            '</body></html>'
        )
        sub_page_html = make_html(json_ld=SINGLE_EVENT_JSONLD)

        with patch("ingestion.sources.generic.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = sub_page_html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            events = adapter._parse_follow_links(listing_html)

        assert mock_get.call_count == 2
        assert len(events) == 2

    def test_sets_ticket_url_from_subpage(self):
        """Events without a ticket_url should get the sub-page URL."""
        adapter = self._make_adapter()
        # JSON-LD event with no url field
        no_url_jsonld = json.dumps({
            "@type": "MusicEvent",
            "name": "Mystery Show",
            "startDate": "2026-04-01T20:00:00",
            "location": {"name": "Cool Venue"},
        })
        listing_html = make_html(event_links=["/shows/mystery"])
        sub_page_html = make_html(json_ld=no_url_jsonld)

        with patch("ingestion.sources.generic.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = sub_page_html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            events = adapter._parse_follow_links(listing_html)

        assert len(events) == 1
        assert events[0]["ticket_url"] == "https://example.com/shows/mystery"


class TestProbeSourceFollowLinks:
    """Test that probe_source recommends follow_links for listing pages."""

    def test_detects_follow_links(self):
        """Listing page with event links whose sub-pages have JSON-LD."""
        listing_html = make_html(
            event_links=["/shows/event-1", "/shows/event-2"]
        )
        sub_page_html = make_html(json_ld=SINGLE_EVENT_JSONLD)

        def mock_fetch(url):
            if "event-1" in url:
                return sub_page_html, MagicMock()
            return listing_html, MagicMock()

        with patch("ingestion.discovery.fetch_page", side_effect=mock_fetch):
            result = probe_source("https://example.com/shows")

        assert result is not None
        assert result["strategy"] == "follow_links"
        assert result["sub_strategy"] == "json_ld"

    def test_prefers_inline_jsonld(self):
        """If the listing page itself has JSON-LD events, prefer json_ld strategy."""
        html = make_html(
            json_ld=MULTI_EVENT_JSONLD,
            event_links=["/shows/event-1"]
        )

        with patch("ingestion.discovery.fetch_page", return_value=(html, MagicMock())):
            result = probe_source("https://example.com/shows")

        assert result is not None
        assert result["strategy"] == "json_ld"  # Not follow_links
