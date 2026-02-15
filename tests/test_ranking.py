"""Tests for scoring and selection logic."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from unittest.mock import MagicMock

from ranking.scorer import (
    score_taste, score_convenience, score_social, score_novelty,
    load_preferences, load_venues,
)


def _make_event(**kwargs):
    """Create a mock event for testing."""
    ev = MagicMock()
    ev.title = kwargs.get("title", "Test Event")
    ev.venue_name = kwargs.get("venue_name", "Village Vanguard")
    ev.category = kwargs.get("category", "jazz")
    ev.neighborhood = kwargs.get("neighborhood", "West Village")
    ev.start_dt = kwargs.get("start_dt", datetime(2025, 3, 15, 20, 30))
    ev.end_dt = kwargs.get("end_dt", None)
    ev.price_min = kwargs.get("price_min", 25.0)
    ev.price_max = kwargs.get("price_max", None)
    ev.entities = kwargs.get("entities", [])
    ev.id = kwargs.get("id", 1)
    return ev


class TestTasteScore:
    def setup_method(self):
        self.prefs = load_preferences()
        self.venues = load_venues()

    def test_jazz_at_vanguard_scores_high(self):
        ev = _make_event(venue_name="Village Vanguard", category="jazz")
        score = score_taste(ev, self.prefs, self.venues)
        assert score >= 20  # Jazz category + venue boost + vibe match

    def test_unknown_venue_scores_lower(self):
        ev = _make_event(venue_name="Random Bar", category="jazz")
        score = score_taste(ev, self.prefs, self.venues)
        assert score < 20

    def test_touristy_venue_penalized(self):
        ev_touristy = _make_event(venue_name="Blue Note", category="jazz")
        ev_intimate = _make_event(venue_name="The Jazz Gallery", category="jazz")
        score_touristy = score_taste(ev_touristy, self.prefs, self.venues)
        score_intimate = score_taste(ev_intimate, self.prefs, self.venues)
        assert score_intimate > score_touristy


class TestConvenienceScore:
    def setup_method(self):
        self.prefs = load_preferences()
        self.venues = load_venues()

    def test_weeknight_830pm_good(self):
        ev = _make_event(start_dt=datetime(2025, 3, 12, 20, 30))  # Wednesday 8:30 PM
        score = score_convenience(ev, self.prefs, self.venues)
        assert score >= 15

    def test_weekend_evening_good(self):
        ev = _make_event(start_dt=datetime(2025, 3, 15, 21, 0))  # Saturday 9 PM
        score = score_convenience(ev, self.prefs, self.venues)
        assert score >= 15

    def test_home_neighborhood_bonus(self):
        ev = _make_event(
            venue_name="Village Vanguard",
            start_dt=datetime(2025, 3, 15, 20, 30),
        )
        score = score_convenience(ev, self.prefs, self.venues)
        assert score >= 20  # Close to home


class TestSocialScore:
    def setup_method(self):
        self.prefs = load_preferences()
        self.venues = load_venues()

    def test_date_friendly_bonus(self):
        ev = _make_event(venue_name="Village Vanguard")
        score = score_social(ev, self.prefs, self.venues)
        assert score >= 15  # date-friendly + seated + intimate

    def test_unknown_venue_baseline(self):
        ev = _make_event(venue_name="Random Bar")
        score = score_social(ev, self.prefs, self.venues)
        assert 8 <= score <= 12


class TestNoveltyScore:
    def test_new_artist(self):
        entity = MagicMock()
        entity.entity_type = "artist"
        entity.entity_value = "New Artist"

        ev = _make_event(entities=[entity])
        score = score_novelty(ev, seen_artists=set(), seen_venues=set())
        assert score >= 10

    def test_seen_artist_lower(self):
        entity = MagicMock()
        entity.entity_type = "artist"
        entity.entity_value = "Repeat Artist"

        ev = _make_event(entities=[entity])
        score_seen = score_novelty(ev, seen_artists={"repeat artist"}, seen_venues=set())
        score_new = score_novelty(ev, seen_artists=set(), seen_venues=set())
        assert score_seen < score_new


class TestOverallScoring:
    def test_ideal_event_scores_above_threshold(self):
        """A jazz event at the Vanguard on a weeknight should easily pass min_score."""
        prefs = load_preferences()
        venues = load_venues()
        ev = _make_event(
            venue_name="Village Vanguard",
            category="jazz",
            start_dt=datetime(2025, 3, 12, 20, 30),
        )
        taste = score_taste(ev, prefs, venues)
        conv = score_convenience(ev, prefs, venues)
        social = score_social(ev, prefs, venues)
        novelty = score_novelty(ev)
        total = taste + conv + social + novelty
        min_score = prefs.get("selection", {}).get("min_score", 25)
        assert total >= min_score
