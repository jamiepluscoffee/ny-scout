"""Tests for scoring and selection logic."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from unittest.mock import MagicMock, patch

from ranking.scorer import (
    score_taste, score_convenience, score_social, score_novelty,
    load_preferences, load_venues, concert_history_signal,
)
from ranking.explainer import match_reasons


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

    def test_no_artist_match_scores_zero(self):
        """Events with no artist affinity get 0 taste score."""
        ev = _make_event(venue_name="Village Vanguard", category="jazz")
        score = score_taste(ev, self.prefs, self.venues)
        assert score == 0  # No artist entities = no taste signal

    def test_artist_match_scores_positive(self):
        """Events with a matched artist get a positive taste score."""
        entity = MagicMock()
        entity.entity_type = "artist"
        entity.entity_value = "Radiohead"
        ev = _make_event(entities=[entity])
        score = score_taste(ev, self.prefs, self.venues)
        assert score > 0


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


class TestConcertHistorySignal:
    """Tests for concert_history_signal scoring."""

    MOCK_PROFILE = {
        "concert_history": {
            "artists": {
                "Makaya McCraven": {"affinity": 0.9, "seen": 3},
                "IDLES": {"affinity": 0.9, "seen": 3},
                "Jon Hopkins": {"affinity": 0.7, "seen": 1},
            },
        },
    }

    def _artist_entity(self, name):
        entity = MagicMock()
        entity.entity_type = "artist"
        entity.entity_value = name
        return entity

    @patch("ranking.scorer._load_taste_profile")
    def test_known_artist_scores_positive(self, mock_profile):
        mock_profile.return_value = self.MOCK_PROFILE
        ev = _make_event(entities=[self._artist_entity("Makaya McCraven")])
        prefs = load_preferences()
        venues = load_venues()
        score = concert_history_signal(ev, prefs, venues)
        assert score > 0
        assert score == 9.0  # 0.9 * 10

    @patch("ranking.scorer._load_taste_profile")
    def test_unknown_artist_scores_zero(self, mock_profile):
        mock_profile.return_value = self.MOCK_PROFILE
        ev = _make_event(entities=[self._artist_entity("Unknown Artist")])
        prefs = load_preferences()
        venues = load_venues()
        score = concert_history_signal(ev, prefs, venues)
        assert score == 0.0

    @patch("ranking.scorer._load_taste_profile")
    def test_repeat_artist_scores_higher(self, mock_profile):
        mock_profile.return_value = self.MOCK_PROFILE
        prefs = load_preferences()
        venues = load_venues()

        ev_repeat = _make_event(entities=[self._artist_entity("IDLES")])
        ev_single = _make_event(entities=[self._artist_entity("Jon Hopkins")])

        score_repeat = concert_history_signal(ev_repeat, prefs, venues)
        score_single = concert_history_signal(ev_single, prefs, venues)
        assert score_repeat > score_single  # 0.9 > 0.7

    @patch("ranking.scorer._load_taste_profile")
    def test_no_entities_scores_zero(self, mock_profile):
        mock_profile.return_value = self.MOCK_PROFILE
        ev = _make_event(entities=[])
        prefs = load_preferences()
        venues = load_venues()
        score = concert_history_signal(ev, prefs, venues)
        assert score == 0.0


class TestConcertMatchReasons:
    """Tests for 'Seen live' match reasons from concert history."""

    TASTE_DATA = {
        "concert_history": {
            "artists": {
                "IDLES": {"affinity": 0.9, "seen": 3},
                "Jon Hopkins": {"affinity": 0.7, "seen": 1},
            },
        },
    }

    def _artist_entity(self, name):
        entity = MagicMock()
        entity.entity_type = "artist"
        entity.entity_value = name
        return entity

    def _mock_open_taste(self, *args, **kwargs):
        """Return a mock file that yields our test YAML data."""
        import io
        import yaml as _yaml
        content = _yaml.dump(self.TASTE_DATA)
        return io.StringIO(content)

    @patch("builtins.open")
    def test_seen_live_in_reasons(self, mock_open):
        mock_open.side_effect = self._mock_open_taste
        ev = _make_event(entities=[self._artist_entity("Jon Hopkins")])
        scores = {
            "signals": {
                "concert_history": 7.0,
                "artist_affinity": 0,
                "venue_reputation": 0,
                "category_weight": 0,
                "home_neighborhood": False,
            },
        }
        reasons = match_reasons(ev, scores, prefs={}, venues={})
        assert any("Seen live" in r for r in reasons)

    @patch("builtins.open")
    def test_seen_live_count_shown(self, mock_open):
        mock_open.side_effect = self._mock_open_taste
        ev = _make_event(entities=[self._artist_entity("IDLES")])
        scores = {
            "signals": {
                "concert_history": 9.0,
                "artist_affinity": 0,
                "venue_reputation": 0,
                "category_weight": 0,
                "home_neighborhood": False,
            },
        }
        reasons = match_reasons(ev, scores, prefs={}, venues={})
        assert "Seen live 3x" in reasons


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
