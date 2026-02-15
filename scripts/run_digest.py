#!/usr/bin/env python3
"""CLI entry point: rank events, generate digest, send email + update web."""
import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from db.models import init_db
from ranking.selector import select_all
from digest.renderer import render_html, render_subject
from digest.email_sender import send_email
from digest.web_renderer import render_web


def main():
    parser = argparse.ArgumentParser(description="NYC Scout — Generate and send daily digest")
    parser.add_argument("--dry-run", action="store_true", help="Print digest to stdout, don't send email")
    parser.add_argument("--no-web", action="store_true", help="Skip web page generation")
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
    digest_data = select_all()

    tonight_count = len(digest_data["tonight"])
    week_count = len(digest_data["this_week"])
    has_wildcard = digest_data["wildcard"] is not None
    logger.info(f"Selected: {tonight_count} tonight, {week_count} this week, wildcard={'yes' if has_wildcard else 'no'}")

    if tonight_count == 0 and week_count == 0:
        logger.warning("No events to include in digest. Skipping.")
        return

    subject = render_subject(digest_data)
    html = render_html(digest_data)

    if args.dry_run:
        print(f"Subject: {subject}\n")
        print(html)
    else:
        sent = send_email(subject, html)
        if sent:
            logger.info("Email digest sent successfully")
        else:
            logger.error("Failed to send email digest")

    # Generate web page
    if not args.no_web:
        web_path = render_web(digest_data)
        logger.info(f"Web page generated: {web_path}")

    print(f"\nDigest: {tonight_count} tonight, {week_count} this week"
          f"{', 1 wildcard' if has_wildcard else ''}")


if __name__ == "__main__":
    main()
