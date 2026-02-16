#!/usr/bin/env python3
"""Parse Songkick gigography HTML into concert history taste signal.

Reads saved Songkick gigography HTML files, extracts artist/venue/date for
each concert attended, and writes structured data to taste_profile.yaml.

Festivals (10+ performers) are skipped — those are ambient exposure, not
intentional choices. Regular multi-act shows (2-9 artists) credit each artist.

Also boosts artist_affinities for concert artists so the listening_history
signal benefits from live attendance data.

Usage:
  python3 scripts/sync_concert_history.py -v
  python3 scripts/sync_concert_history.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default source files (relative to project root)
SOURCE_FILES = [
    "Gigography2_files/Gigography1.htm",
    "Gigography2.htm",
]

# Festival threshold — events with this many or more performers are skipped
FESTIVAL_THRESHOLD = 10

# Affinity calculation
BASE_AFFINITY = 0.7
REPEAT_BONUS = 0.1
MAX_AFFINITY = 1.0

# Artist affinity boost for concert artists
AFFINITY_BOOST = 0.15
AFFINITY_DEFAULT = 0.6


def parse_gigography_html(filepath: str) -> list[dict]:
    """Parse a Songkick gigography HTML file.

    Extracts concert data from embedded JSON-LD scripts.
    Returns list of dicts with keys: artists, venue, date, city, title.
    """
    with open(filepath, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    concerts = []
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string)
        except (json.JSONDecodeError, TypeError):
            continue

        # JSON-LD is wrapped in a list
        if isinstance(data, list):
            data = data[0]

        if not isinstance(data, dict):
            continue

        performers = data.get("performer", [])
        if not isinstance(performers, list):
            performers = [performers]

        artist_names = [p.get("name", "") for p in performers if p.get("name")]

        # Skip festivals (10+ performers)
        if len(artist_names) >= FESTIVAL_THRESHOLD:
            event_name = data.get("name", "Unknown")
            logger.debug(f"  Skipping festival ({len(artist_names)} artists): {event_name}")
            continue

        location = data.get("location", {})
        venue_name = location.get("name", "")
        address = location.get("address", {})
        city = address.get("addressLocality", "")
        country = address.get("addressCountry", "")
        date = data.get("startDate", "")

        # Extract just the date part (YYYY-MM-DD) from datetime strings
        if "T" in date:
            date = date.split("T")[0]

        concerts.append({
            "artists": artist_names,
            "venue": venue_name,
            "date": date,
            "city": f"{city}, {country}" if country else city,
            "title": data.get("name", ""),
        })

    logger.info(f"  Parsed {len(concerts)} concerts from {os.path.basename(filepath)}")
    return concerts


def compute_artist_stats(all_concerts: list[dict]) -> dict[str, dict]:
    """Compute per-artist attendance counts and affinities.

    Returns dict mapping artist name to {affinity, seen}.
    """
    artist_counts: dict[str, int] = {}
    for concert in all_concerts:
        for artist in concert["artists"]:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1

    artists = {}
    for name, count in sorted(artist_counts.items(), key=lambda x: (-x[1], x[0])):
        affinity = min(BASE_AFFINITY + REPEAT_BONUS * (count - 1), MAX_AFFINITY)
        artists[name] = {"affinity": round(affinity, 1), "seen": count}

    return artists


def boost_artist_affinities(
    existing_affinities: dict[str, float],
    manual_artists: list[str],
    concert_artists: dict[str, dict],
) -> tuple[dict[str, float], list[str]]:
    """Boost artist_affinities for artists seen live.

    - Existing artists: +0.15 (capped at 1.0)
    - New artists: added at 0.6
    - All concert artists added to manual_artists so Last.fm sync won't overwrite
    """
    boosted = dict(existing_affinities)
    manual_set = set(manual_artists)

    for name in concert_artists:
        if name in boosted:
            boosted[name] = min(1.0, round(boosted[name] + AFFINITY_BOOST, 3))
        else:
            boosted[name] = AFFINITY_DEFAULT
        manual_set.add(name)

    # Re-sort by affinity descending
    boosted = dict(sorted(boosted.items(), key=lambda x: -x[1]))

    return boosted, sorted(manual_set)


def sync_concert_history(dry_run: bool = False) -> dict:
    """Parse Songkick HTML files and write concert history to taste_profile.yaml."""
    # Parse all source files
    all_concerts = []
    for relpath in SOURCE_FILES:
        filepath = os.path.join(PROJECT_DIR, relpath)
        if not os.path.exists(filepath):
            logger.warning(f"  Source file not found: {relpath}")
            continue
        all_concerts.extend(parse_gigography_html(filepath))

    if not all_concerts:
        logger.error("No concerts parsed from any source file")
        return {"total_concerts": 0}

    # Compute artist stats
    artist_stats = compute_artist_stats(all_concerts)
    total_concerts = len(all_concerts)

    logger.info(f"  {total_concerts} concerts, {len(artist_stats)} unique artists")

    # Show top artists
    for name, stats in list(artist_stats.items())[:15]:
        logger.info(f"    {stats['seen']}x  {stats['affinity']:.1f}  {name}")
    if len(artist_stats) > 15:
        logger.info(f"    ... and {len(artist_stats) - 15} more")

    if dry_run:
        logger.info("[DRY RUN] Would write concert_history and boost affinities")
        return {"total_concerts": total_concerts, "unique_artists": len(artist_stats)}

    # Load existing taste profile
    path = os.path.join(CONFIG_DIR, "taste_profile.yaml")
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # Write concert_history section
    # Convert artist stats to simple dicts for YAML serialization
    concert_artists_yaml = {}
    for name, stats in artist_stats.items():
        concert_artists_yaml[name] = {
            "affinity": stats["affinity"],
            "seen": stats["seen"],
        }

    data["concert_history"] = {
        "artists": concert_artists_yaml,
        "total_concerts": total_concerts,
        "source": "songkick",
        "source_files": list(SOURCE_FILES),
    }

    # Boost artist_affinities
    existing_affinities = data.get("artist_affinities", {})
    manual_artists = data.get("manual_artists", [])
    boosted_affinities, updated_manual = boost_artist_affinities(
        existing_affinities, manual_artists, artist_stats,
    )
    data["artist_affinities"] = boosted_affinities
    data["manual_artists"] = updated_manual

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)

    logger.info(f"Wrote concert_history ({total_concerts} concerts) to taste_profile.yaml")
    logger.info(f"Boosted {len(artist_stats)} artists in artist_affinities")

    return {"total_concerts": total_concerts, "unique_artists": len(artist_stats)}


def main():
    parser = argparse.ArgumentParser(
        description="Parse Songkick gigography → concert history in taste_profile.yaml"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("Parsing Songkick gigography...")
    stats = sync_concert_history(dry_run=args.dry_run)

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Done: {stats['total_concerts']} concerts, "
          f"{stats.get('unique_artists', 0)} unique artists")


if __name__ == "__main__":
    main()
