"""Event scoring based on user preferences."""
from __future__ import annotations

import os
from datetime import datetime

import yaml
from rapidfuzz import fuzz

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")


def load_preferences() -> dict:
    path = os.path.join(CONFIG_DIR, "preferences.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def load_venues() -> dict:
    path = os.path.join(CONFIG_DIR, "venues.yaml")
    with open(path) as f:
        return yaml.safe_load(f).get("venues", {})


def get_venue_info(venue_name: str, venues: dict) -> dict | None:
    """Fuzzy match venue name against venues.yaml."""
    for name, info in venues.items():
        if fuzz.ratio(venue_name.lower(), name.lower()) > 85:
            return info
    return None


def _load_taste_profile() -> dict:
    """Load taste profile data (artist affinities, etc.)."""
    path = os.path.join(CONFIG_DIR, "taste_profile.yaml")
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


# -- Taste signals --
# Each signal takes (event, prefs, venues) and returns a float sub-score.
# To add a new taste signal, define a function and add it to TASTE_SIGNALS.

def category_signal(event, prefs: dict, venues: dict) -> float:
    """Score 0-15 based on category preference weight."""
    cat_weights = prefs.get("category_weights", {})
    category = event.category.lower() if event.category else ""
    return cat_weights.get(category, 0.3) * 15


def venue_reputation_signal(event, prefs: dict, venues: dict) -> float:
    """Score 0-10 based on venue boost from preferences."""
    venue_boosts = prefs.get("venue_boost", {})
    for vname, boost in venue_boosts.items():
        if fuzz.ratio(event.venue_name.lower(), vname.lower()) > 85:
            return float(boost)
    return 0.0


def vibe_alignment_signal(event, prefs: dict, venues: dict) -> float:
    """Score -8 to 15 based on vibe tag overlap with preferences."""
    score = 0.0
    venue_info = get_venue_info(event.venue_name, venues)
    if venue_info:
        vibe_tags = set(venue_info.get("vibe_tags", []))
        preferred_vibes = set(prefs.get("vibe_preferences", []))
        if vibe_tags & preferred_vibes:
            overlap = len(vibe_tags & preferred_vibes)
            score += min(overlap * 5, 15)
        if "touristy" in vibe_tags and "not-touristy" in preferred_vibes:
            score -= 8
    return score


def listening_history_signal(event, prefs: dict, venues: dict) -> float:
    """Score 0-10 based on artist affinity from Last.fm listening history.

    Matches event performers against artist_affinities in taste_profile.yaml.
    Uses fuzzy matching (85% threshold) to handle name variations.
    Takes the highest affinity among all performers on the event.
    """
    profile = _load_taste_profile()
    affinities = profile.get("artist_affinities", {})
    if not affinities:
        return 0.0

    # Get artist names from event entities
    artist_names = [e.entity_value for e in event.entities if e.entity_type == "artist"]
    if not artist_names:
        return 0.0

    best_score = 0.0
    for artist in artist_names:
        artist_lower = artist.lower()
        for known_artist, affinity in affinities.items():
            if fuzz.ratio(artist_lower, known_artist.lower()) > 85:
                best_score = max(best_score, float(affinity))
                break

    # Scale affinity (0-1) to signal score (0-10)
    return round(best_score * 10, 1)


# Ordered list of taste signals. Add new signals here.
TASTE_SIGNALS = [
    category_signal,         # 0-15
    venue_reputation_signal, # 0-10
    vibe_alignment_signal,   # -8 to 15
    listening_history_signal,  # 0-10 (placeholder)
]


def score_taste(event, prefs: dict, venues: dict) -> float:
    """Score 0-40 based on pluggable taste signals."""
    score = sum(signal(event, prefs, venues) for signal in TASTE_SIGNALS)
    return max(0, min(score, 40))


def score_convenience(event, prefs: dict, venues: dict) -> float:
    """Score 0-25 based on time-of-day and travel."""
    score = 15.0  # Start with a baseline

    start_dt = event.start_dt
    if not isinstance(start_dt, datetime):
        return score

    hour = start_dt.hour
    weekday = start_dt.weekday()  # 0=Mon, 6=Sun
    is_weekend = weekday >= 4  # Fri-Sun

    # Time-of-day fit (0-15)
    if is_weekend:
        cutoff_str = prefs.get("weekend_late_cutoff", "23:30")
        # Weekend: 18-23 ideal
        if 18 <= hour <= 23:
            score += 10
        elif hour > 23:
            score += 3
    else:
        cutoff_str = prefs.get("weekday_late_cutoff", "22:30")
        cutoff_hour = int(cutoff_str.split(":")[0])
        # Weeknight: 19-21 ideal
        if 19 <= hour <= 21:
            score += 10
        elif hour <= cutoff_hour:
            score += 5
        else:
            score -= 5  # Too late for a weeknight

    # Travel penalty — rough neighborhood distance heuristic
    home = prefs.get("home_neighborhood", "").lower()
    venue_info = get_venue_info(event.venue_name, venues)
    if venue_info:
        venue_hood = venue_info.get("neighborhood", "").lower()
        if home == venue_hood:
            score += 5  # No travel
        elif venue_hood in ("west village", "greenwich village", "flatiron", "chelsea"):
            score += 3  # Close-ish to West Village
        elif venue_hood in ("east village", "lower east side", "soho"):
            score += 1
        # Further neighborhoods get no bonus

    return max(0, min(score, 25))


def score_social(event, prefs: dict, venues: dict) -> float:
    """Score 0-20 based on social/date fit."""
    score = 10.0

    venue_info = get_venue_info(event.venue_name, venues)
    if venue_info:
        vibe_tags = venue_info.get("vibe_tags", [])
        if "date-friendly" in vibe_tags:
            score += 5
        if venue_info.get("seated"):
            score += 3
        capacity = venue_info.get("capacity")
        if capacity and capacity <= 100:
            score += 2  # Intimate

    # Duration penalty if event is very long
    if event.end_dt and event.start_dt:
        try:
            duration_h = (event.end_dt - event.start_dt).total_seconds() / 3600
            if duration_h > 3:
                score -= 3
        except TypeError:
            pass

    return max(0, min(score, 20))


def score_novelty(event, seen_artists: set = None, seen_venues: set = None) -> float:
    """Score 0-15 based on novelty."""
    score = 7.0  # Baseline
    seen_artists = seen_artists or set()
    seen_venues = seen_venues or set()

    # New artist bonus
    artist_names = [e.entity_value for e in event.entities if e.entity_type == "artist"]
    if artist_names:
        if not any(a.lower() in seen_artists for a in artist_names):
            score += 5
    else:
        score += 3  # Unknown artist — might be novel

    # Venue variety bonus
    if event.venue_name.lower() not in seen_venues:
        score += 3

    return max(0, min(score, 15))


def score_event(event, prefs: dict = None, venues: dict = None,
                seen_artists: set = None, seen_venues: set = None) -> dict:
    """Compute full score breakdown for an event."""
    prefs = prefs or load_preferences()
    venues = venues or load_venues()

    taste = score_taste(event, prefs, venues)
    convenience = score_convenience(event, prefs, venues)
    social = score_social(event, prefs, venues)
    novelty = score_novelty(event, seen_artists, seen_venues)
    total = taste + convenience + social + novelty

    return {
        "total": round(total, 1),
        "taste": round(taste, 1),
        "convenience": round(convenience, 1),
        "social": round(social, 1),
        "novelty": round(novelty, 1),
    }
