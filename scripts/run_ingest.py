#!/usr/bin/env python3
"""CLI entry point: run ingestion for all (or one) source."""
import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from ingestion.runner import run_ingestion
from ingestion.discovery import run_discovery, add_link


def main():
    parser = argparse.ArgumentParser(description="NYC Scout — Ingest events from sources")
    parser.add_argument("--source", "-s", help="Run only this source (by name)")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="Process pending links from discovered_links.yaml")
    parser.add_argument("--add-link", metavar="URL",
                        help="Add a URL to discovered_links.yaml and process it")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Handle discovery mode
    if args.add_link:
        add_link(args.add_link)
        d_stats = run_discovery()
        print(f"\nDiscovery: {d_stats['processed']} links processed, "
              f"{d_stats['sources_registered']} new sources, "
              f"{d_stats['events_found']} events found")
        if d_stats["unclear"] > 0:
            print(f"  {d_stats['unclear']} links need clarification — check discovered_links.yaml")
        return

    if args.discover:
        d_stats = run_discovery()
        print(f"\nDiscovery: {d_stats['processed']} links processed, "
              f"{d_stats['sources_registered']} new sources, "
              f"{d_stats['events_found']} events found")
        if d_stats["unclear"] > 0:
            print(f"  {d_stats['unclear']} links need clarification — check discovered_links.yaml")
        return

    # Normal ingestion
    stats = run_ingestion(source_filter=args.source)
    print(f"\nIngestion complete: {stats['success']} sources OK, "
          f"{stats['failed']} failed, {stats['events_stored']} new events stored")

    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
