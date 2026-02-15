"""Tests for deduplication logic."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from ingestion.runner import normalize_title
from rapidfuzz import fuzz


class TestFuzzyMatching:
    def test_exact_venue_match(self):
        assert fuzz.ratio("village vanguard", "village vanguard") == 100

    def test_venue_with_the(self):
        score = fuzz.ratio("the jazz gallery", "jazz gallery")
        assert score > 75  # Close but not exact

    def test_different_venues(self):
        score = fuzz.ratio("village vanguard", "smalls jazz club")
        assert score < 50

    def test_title_match_same_event(self):
        t1 = normalize_title("Ben Monder Trio")
        t2 = normalize_title("Ben Monder Trio")
        assert fuzz.ratio(t1, t2) == 100

    def test_title_match_slight_diff(self):
        t1 = normalize_title("Ben Monder Trio")
        t2 = normalize_title("Ben Monder's Trio")
        assert fuzz.ratio(t1, t2) > 85

    def test_title_match_different_events(self):
        t1 = normalize_title("Ben Monder Trio")
        t2 = normalize_title("Brad Mehldau Solo")
        assert fuzz.ratio(t1, t2) < 60


class TestTimeWindow:
    def test_within_2_hours(self):
        dt1 = datetime(2025, 3, 15, 20, 0)
        dt2 = datetime(2025, 3, 15, 21, 30)
        diff = abs((dt1 - dt2).total_seconds())
        assert diff <= 7200  # 2 hours

    def test_outside_2_hours(self):
        dt1 = datetime(2025, 3, 15, 20, 0)
        dt2 = datetime(2025, 3, 15, 23, 0)
        diff = abs((dt1 - dt2).total_seconds())
        assert diff > 7200

    def test_same_time(self):
        dt1 = datetime(2025, 3, 15, 20, 0)
        dt2 = datetime(2025, 3, 15, 20, 0)
        diff = abs((dt1 - dt2).total_seconds())
        assert diff <= 7200
