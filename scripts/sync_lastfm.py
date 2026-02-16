#!/usr/bin/env python3
"""Sync Last.fm listening data into taste_profile.yaml.

Pulls two signals:
  1. All-time top artists (100+ plays) — base affinity from play count
  2. Recent top artists (last 6 months) — recency boost

Manual overrides in taste_profile.yaml are preserved and take priority.

Usage:
  python3 scripts/sync_lastfm.py
  python3 scripts/sync_lastfm.py -v          # verbose
  python3 scripts/sync_lastfm.py --dry-run   # show what would change
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
LASTFM_API = "https://ws.audioscrobbler.com/2.0/"

# Tuning parameters
MIN_ALLTIME_PLAYS = 200       # Minimum plays to be included from all-time
ALLTIME_LIMIT = 500           # Max artists to fetch from all-time
RECENT_PERIOD = "6month"      # Last.fm period for recency
RECENT_LIMIT = 100            # Max recent artists to fetch
RECENT_BOOST_MAX = 0.3        # Max bonus for recent listening
LASTFM_USERNAME = "dustpunk"


def fetch_top_artists(api_key: str, period: str = "overall",
                      limit: int = 200) -> list[dict]:
    """Fetch top artists from Last.fm for a given period."""
    all_artists = []
    page = 1
    per_page = min(limit, 200)  # Last.fm max per page

    while len(all_artists) < limit:
        resp = requests.get(LASTFM_API, params={
            "method": "user.gettopartists",
            "user": LASTFM_USERNAME,
            "api_key": api_key,
            "format": "json",
            "period": period,
            "limit": per_page,
            "page": page,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        artists = data.get("topartists", {}).get("artist", [])
        if not artists:
            break

        all_artists.extend(artists)
        total_pages = int(data["topartists"]["@attr"]["totalPages"])
        if page >= total_pages:
            break
        page += 1

    return all_artists[:limit]


def compute_affinities(alltime: list[dict], recent: list[dict]) -> dict[str, float]:
    """Compute artist affinity scores from Last.fm data.

    Strategy:
      - Base score: log-scaled play count relative to top artist (0.1 – 0.85)
        Using log scale so the long tail isn't completely flat.
      - Recency boost: up to +0.3 for artists high in recent charts.
      - Combined score capped at 1.0.
    """
    if not alltime:
        return {}

    # Filter all-time to minimum plays
    alltime = [a for a in alltime if int(a["playcount"]) >= MIN_ALLTIME_PLAYS]
    if not alltime:
        return {}

    max_plays = int(alltime[0]["playcount"])
    log_max = math.log1p(max_plays)

    # Base affinities from all-time plays (log-scaled)
    affinities = {}
    for a in alltime:
        plays = int(a["playcount"])
        # log scale: log(plays) / log(max) gives 0.0–1.0, then scale to 0.1–0.85
        log_score = math.log1p(plays) / log_max
        base = 0.1 + (log_score * 0.75)
        affinities[a["name"]] = round(base, 3)

    # Recency boost
    if recent:
        max_recent = int(recent[0]["playcount"])
        for i, a in enumerate(recent):
            name = a["name"]
            recent_plays = int(a["playcount"])
            # Boost scales with position in recent chart and play count
            position_factor = 1.0 - (i / len(recent))  # 1.0 for #1, 0.0 for last
            play_factor = recent_plays / max_recent
            boost = RECENT_BOOST_MAX * position_factor * play_factor

            if name in affinities:
                affinities[name] = min(1.0, round(affinities[name] + boost, 3))
            elif recent_plays >= 50:
                # Artist not in all-time top but listened to recently
                affinities[name] = round(0.3 + boost, 3)

    return affinities


def sync_taste_profile(affinities: dict[str, float], dry_run: bool = False) -> dict:
    """Merge computed affinities into taste_profile.yaml.

    Manual overrides (existing entries) are preserved and take priority.
    Returns stats dict.
    """
    path = os.path.join(CONFIG_DIR, "taste_profile.yaml")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    existing = data.get("artist_affinities", {}) or {}
    manual = data.get("manual_overrides", set())

    # Track which entries were manually set (existed before any sync)
    # On first sync, all existing entries are considered manual
    if "lastfm_synced" not in data:
        manual_artists = set(existing.keys())
    else:
        manual_artists = set(data.get("manual_artists", []))

    # Merge: manual overrides win
    merged = {}
    new_count = 0
    updated_count = 0

    for name, score in affinities.items():
        if name in manual_artists:
            merged[name] = existing[name]  # Keep manual value
            logger.debug(f"  {name}: keeping manual override ({existing[name]})")
        elif name in existing:
            if existing[name] != score:
                updated_count += 1
            merged[name] = score
        else:
            merged[name] = score
            new_count += 1

    # Keep any manual entries not in the new affinities
    for name in manual_artists:
        if name not in merged and name in existing:
            merged[name] = existing[name]

    # Sort by affinity descending
    merged = dict(sorted(merged.items(), key=lambda x: -x[1]))

    stats = {
        "total_artists": len(merged),
        "new": new_count,
        "updated": updated_count,
        "manual_preserved": len(manual_artists),
    }

    if dry_run:
        logger.info(f"Dry run — would write {len(merged)} artists")
        for name, score in list(merged.items())[:20]:
            flag = " (manual)" if name in manual_artists else ""
            logger.info(f"  {score:.3f}  {name}{flag}")
        if len(merged) > 20:
            logger.info(f"  ... and {len(merged) - 20} more")
        return stats

    data["artist_affinities"] = merged
    data["lastfm_synced"] = True
    data["lastfm_username"] = LASTFM_USERNAME
    data["manual_artists"] = sorted(manual_artists)

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)

    logger.info(f"Wrote {len(merged)} artist affinities to taste_profile.yaml")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Sync Last.fm listening data → taste_profile.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    api_key = os.getenv("LASTFM_API_KEY")
    if not api_key:
        print("Error: LASTFM_API_KEY not set in .env")
        sys.exit(1)

    print("Fetching all-time top artists...")
    alltime = fetch_top_artists(api_key, period="overall", limit=ALLTIME_LIMIT)
    print(f"  Got {len(alltime)} artists")

    print(f"Fetching recent artists ({RECENT_PERIOD})...")
    recent = fetch_top_artists(api_key, period=RECENT_PERIOD, limit=RECENT_LIMIT)
    print(f"  Got {len(recent)} artists")

    print("Computing affinities...")
    affinities = compute_affinities(alltime, recent)
    print(f"  {len(affinities)} artists above threshold")

    stats = sync_taste_profile(affinities, dry_run=args.dry_run)
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Sync complete: "
          f"{stats['total_artists']} total, {stats['new']} new, "
          f"{stats['updated']} updated, {stats['manual_preserved']} manual overrides preserved")


if __name__ == "__main__":
    main()
