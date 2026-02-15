"""Tests for title normalization and date parsing."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from ingestion.runner import normalize_title
from ingestion.base import BaseAdapter


class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("Ben Monder Trio") == "ben monder trio"

    def test_strip_punctuation(self):
        assert normalize_title("Ben Monder's Trio!!!") == "ben monders trio"

    def test_collapse_whitespace(self):
        assert normalize_title("  Ben   Monder   Trio  ") == "ben monder trio"

    def test_mixed(self):
        assert normalize_title("  The Jazz @ Gallery: Live! ") == "the jazz gallery live"


class TestParseDatetime:
    def test_iso_format(self):
        dt = BaseAdapter.parse_datetime("2025-03-15T20:30:00")
        assert dt == datetime(2025, 3, 15, 20, 30, 0)

    def test_iso_with_z(self):
        dt = BaseAdapter.parse_datetime("2025-03-15T20:30:00Z")
        assert dt == datetime(2025, 3, 15, 20, 30, 0)

    def test_date_only(self):
        dt = BaseAdapter.parse_datetime("2025-03-15")
        assert dt == datetime(2025, 3, 15, 0, 0, 0)

    def test_us_format(self):
        dt = BaseAdapter.parse_datetime("03/15/2025 8:30 PM")
        assert dt == datetime(2025, 3, 15, 20, 30, 0)

    def test_long_format(self):
        dt = BaseAdapter.parse_datetime("March 15, 2025 8:30 PM")
        assert dt == datetime(2025, 3, 15, 20, 30, 0)

    def test_invalid(self):
        assert BaseAdapter.parse_datetime("not a date") is None

    def test_empty(self):
        assert BaseAdapter.parse_datetime("") is None

    def test_none(self):
        assert BaseAdapter.parse_datetime(None) is None

    def test_datetime_passthrough(self):
        dt = datetime(2025, 3, 15, 20, 30)
        assert BaseAdapter.parse_datetime(dt) is dt
