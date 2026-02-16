"""Select events for the digest: Tonight, This Week, Coming Up, Wildcard."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from db.models import Event, EventEntity
from ranking.scorer import score_event, load_preferences, load_venues


def get_active_events(start: datetime, end: datetime):
    """Fetch active events in a date range, with entities prefetched."""
    events = list(
        Event.select()
        .where(
            Event.status == "active",
            Event.start_dt >= start,
            Event.start_dt <= end,
        )
        .order_by(Event.start_dt)
    )
    # Prefetch entities
    if events:
        entities = list(
            EventEntity.select().where(EventEntity.event.in_([e.id for e in events]))
        )
        entity_map = {}
        for ent in entities:
            entity_map.setdefault(ent.event_id, []).append(ent)
        for ev in events:
            ev._prefetched_entities = entity_map.get(ev.id, [])
    else:
        for ev in events:
            ev._prefetched_entities = []
    return events


def _patch_entities(event):
    """Make event.entities work with prefetched data."""
    if hasattr(event, "_prefetched_entities"):
        return event._prefetched_entities
    return list(event.entities)


def score_and_rank(events, prefs=None, venues=None, novelty_boost=1.0):
    """Score all events and return sorted (event, scores) pairs."""
    prefs = prefs or load_preferences()
    venues = venues or load_venues()
    seen_artists = set()
    seen_venues = set()

    scored = []
    for ev in events:
        # Patch entities for scoring
        original_entities = ev.entities
        ev.entities = _patch_entities(ev)
        scores = score_event(ev, prefs, venues, seen_artists, seen_venues)
        ev.entities = original_entities

        # Apply novelty boost (for wildcard selection)
        if novelty_boost != 1.0:
            scores["novelty"] *= novelty_boost
            scores["total"] = (
                scores["taste"] + scores["convenience"]
                + scores["social"] + scores["novelty"]
            )

        scored.append((ev, scores))

        # Track seen artists/venues
        for ent in _patch_entities(ev):
            if ent.entity_type == "artist":
                seen_artists.add(ent.entity_value.lower())
        seen_venues.add(ev.venue_name.lower())

    scored.sort(key=lambda x: x[1]["total"], reverse=True)
    return scored


def select_tonight(prefs=None, venues=None) -> list[tuple]:
    """Select top events for tonight (next 24 hours)."""
    prefs = prefs or load_preferences()
    venues = venues or load_venues()
    now = datetime.now()
    end = now + timedelta(hours=24)

    events = get_active_events(now, end)
    scored = score_and_rank(events, prefs, venues)

    min_score = prefs.get("selection", {}).get("min_score", 25)
    count = prefs.get("selection", {}).get("tonight_count", 5)

    return [(ev, s) for ev, s in scored if s["total"] >= min_score][:count]


def select_this_week(prefs=None, venues=None) -> list[tuple]:
    """Select top events for this week (next 7 days), max 2 per venue."""
    prefs = prefs or load_preferences()
    venues = venues or load_venues()
    now = datetime.now()
    end = now + timedelta(days=7)

    events = get_active_events(now, end)
    scored = score_and_rank(events, prefs, venues)

    min_score = prefs.get("selection", {}).get("min_score", 25)
    count = prefs.get("selection", {}).get("week_count", 10)
    max_per_venue = prefs.get("selection", {}).get("max_per_venue_week", 2)

    venue_counts = Counter()
    result = []
    for ev, s in scored:
        if s["total"] < min_score:
            continue
        vn = ev.venue_name.lower()
        if venue_counts[vn] >= max_per_venue:
            continue
        venue_counts[vn] += 1
        result.append((ev, s))
        if len(result) >= count:
            break

    return result


def select_coming_up(prefs=None, venues=None) -> list[tuple]:
    """Select top events 1–6 weeks out (8–42 days), no venue cap.

    These are the 'buy tickets now' picks — events far enough out that
    you have time to plan, but likely to sell out.
    """
    prefs = prefs or load_preferences()
    venues = venues or load_venues()
    now = datetime.now()
    start = now + timedelta(days=8)
    end = now + timedelta(days=90)

    events = get_active_events(start, end)
    scored = score_and_rank(events, prefs, venues)

    min_score = prefs.get("selection", {}).get("min_score", 25)
    count = prefs.get("selection", {}).get("coming_up_count", 5)

    return [(ev, s) for ev, s in scored if s["total"] >= min_score][:count]


def select_wildcard(prefs=None, venues=None) -> tuple | None:
    """Select one wildcard pick with boosted novelty."""
    prefs = prefs or load_preferences()
    venues = venues or load_venues()
    now = datetime.now()
    end = now + timedelta(days=7)

    events = get_active_events(now, end)
    scored = score_and_rank(events, prefs, venues, novelty_boost=3.0)

    min_score = prefs.get("selection", {}).get("min_score", 25)

    for ev, s in scored:
        if s["total"] >= min_score:
            return (ev, s)
    return None


def select_full_list(prefs=None, venues=None) -> list[tuple]:
    """Score all active events in the next 90 days, sorted by total desc.

    No min_score filter — returns everything for the Full List page.
    """
    prefs = prefs or load_preferences()
    venues = venues or load_venues()
    now = datetime.now()
    end = now + timedelta(days=90)

    events = get_active_events(now, end)
    scored = score_and_rank(events, prefs, venues)
    return scored


def _has_artist_signal(scores: dict) -> bool:
    """True if the event has any artist-based scoring signal."""
    signals = scores.get("signals", {})
    return signals.get("artist_affinity", 0) > 0 or signals.get("concert_history", 0) > 0


def split_radar_and_lucky_dip(scored: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    """Split already-scored events into radar (artist signal) and lucky dip (no signal).

    Radar is sorted chronologically; lucky dip keeps score-descending order.
    """
    radar = []
    lucky_dip = []
    for ev, s in scored:
        if _has_artist_signal(s):
            radar.append((ev, s))
        else:
            lucky_dip.append((ev, s))

    radar.sort(key=lambda x: str(x[0].start_dt))
    return radar, lucky_dip


def select_all() -> dict:
    """Run all selectors and return the full digest data."""
    prefs = load_preferences()
    venues = load_venues()
    return {
        "tonight": select_tonight(prefs, venues),
        "this_week": select_this_week(prefs, venues),
        "coming_up": select_coming_up(prefs, venues),
        "wildcard": select_wildcard(prefs, venues),
    }
