#!/usr/bin/env python3
"""CLI entry point: rank events, generate web pages."""
import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from db.models import init_db
from ranking.selector import select_full_list, split_radar_and_lucky_dip
from ranking.scorer import load_preferences, load_venues
from digest.web_renderer import render_web, render_full_list, render_lucky_dip


def main():
    parser = argparse.ArgumentParser(description="NYC Scout — Generate daily web pages")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing files")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("digest")

    init_db()
    prefs = load_preferences()
    venues = load_venues()

    full_list = select_full_list(prefs, venues)
    radar, lucky = split_radar_and_lucky_dip(full_list)

    logger.info(f"Selected: {len(radar)} radar, {len(lucky)} lucky dip, {len(full_list)} total")

    if len(full_list) == 0:
        logger.warning("No events found. Skipping.")
        return

    if args.dry_run:
        print(f"Radar: {len(radar)} events")
        print(f"Lucky Dip: {len(lucky)} events")
        print(f"Full list: {len(full_list)} events")
        return

    web_path = render_web(radar, prefs=prefs, venues=venues)
    logger.info(f"Radar generated: {web_path} ({len(radar)} events)")

    lucky_path = render_lucky_dip(lucky, prefs=prefs, venues=venues)
    logger.info(f"Lucky Dip generated: {lucky_path} ({len(lucky)} events)")

    list_path = render_full_list(full_list, prefs=prefs, venues=venues)
    logger.info(f"Full list generated: {list_path} ({len(full_list)} events)")

    print(f"\nGenerated: {len(radar)} radar, {len(lucky)} lucky dip, {len(full_list)} total")


if __name__ == "__main__":
    main()
