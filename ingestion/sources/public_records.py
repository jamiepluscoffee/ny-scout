"""Public Records (Gowanus, Brooklyn) adapter — HTML scraping."""
import re
from datetime import datetime

from ingestion.scrape_adapter import ScrapeAdapter
from ingestion.base import EventDict


class Adapter(ScrapeAdapter):
    """Scrape the Public Records event calendar."""

    VENUE_NAME = "Public Records"
    ADDRESS = "233 Butler St, Brooklyn, NY 11217"

    def fetch_raw(self) -> str:
        return self.fetch_html()

    def parse(self, raw: str) -> list[EventDict]:
        soup = self.soup(raw)
        events = []
        current_year = datetime.now().year

        for row in soup.select("a.event.table-row"):
            # Ticket URL
            ticket_url = row.get("href", "")

            # Date cell: "Sun 3.8\nClub,\n4:00 pm,\n<span>Sound Room</span>"
            date_cell = row.select_one(".table-cell.date")
            if not date_cell:
                continue

            date_text = date_cell.get_text(" ", strip=True)

            # Extract date like "3.8" or "3.14"
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})", date_text)
            if not date_match:
                continue
            month, day = int(date_match.group(1)), int(date_match.group(2))

            # Extract time like "4:00 pm" or "10:30 pm"
            time_match = re.search(r"(\d{1,2}:\d{2})\s*(am|pm)", date_text, re.IGNORECASE)
            hour, minute = 20, 0  # default 8pm
            if time_match:
                t = datetime.strptime(f"{time_match.group(1)} {time_match.group(2)}", "%I:%M %p")
                hour, minute = t.hour, t.minute

            # Handle year rollover (Dec events listed in Jan)
            year = current_year
            now = datetime.now()
            if month < now.month - 1:
                year += 1

            try:
                start_dt = datetime(year, month, day, hour, minute)
            except ValueError:
                continue

            # Category (Club, Live, Etc)
            cat_match = re.search(r"\b(Club|Live|Etc)\b", date_text, re.IGNORECASE)
            category = "concert"
            if cat_match and cat_match.group(1).lower() == "live":
                category = "concert"

            # Room/location
            locations = [span.get_text(strip=True) for span in date_cell.select("span.location")]
            room = ", ".join(locations) if locations else ""

            # Title
            title_cell = row.select_one(".table-cell.title")
            if not title_cell:
                continue
            # Remove the "Get tickets" span from title text
            for span in title_cell.select("span"):
                span.decompose()
            title = title_cell.get_text(strip=True)
            if not title:
                continue

            event_id = self.make_event_id("public_records", f"{title[:40]}:{month}.{day}")

            # Use title as artist entity (strip "w/" prefixed guest format)
            artists = [a.strip() for a in re.split(r"[,&+]|w/", title) if a.strip()]
            entities = [{"type": "artist", "value": a} for a in artists]

            description = f"{room}" if room else ""

            events.append(EventDict(
                source_event_id=event_id,
                title=title,
                description=description,
                start_dt=start_dt,
                venue_name=self.VENUE_NAME,
                address=self.ADDRESS,
                ticket_url=ticket_url,
                category=category,
                entities=entities,
            ))

        return events
