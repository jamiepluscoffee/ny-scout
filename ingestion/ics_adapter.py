"""Generic ICS calendar fetcher/parser."""
import requests
from icalendar import Calendar

from ingestion.base import BaseAdapter, EventDict


class ICSAdapter(BaseAdapter):
    """Base for sources that provide ICS/iCal feeds."""

    def fetch_ics(self, url: str) -> str:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def parse_ics(self, ics_text: str, source_name: str, venue_name: str) -> list[EventDict]:
        events = []
        cal = Calendar.from_ical(ics_text)
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            uid = str(component.get("uid", ""))
            summary = str(component.get("summary", ""))
            description = str(component.get("description", ""))
            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            location = str(component.get("location", ""))
            url = str(component.get("url", ""))

            start_dt = dtstart.dt if dtstart else None
            end_dt = dtend.dt if dtend else None

            if not summary or not start_dt:
                continue

            events.append(EventDict(
                source_event_id=self.make_event_id(source_name, uid or summary),
                title=summary,
                description=description,
                start_dt=start_dt,
                end_dt=end_dt,
                venue_name=venue_name or location,
                address=location,
                ticket_url=url,
                category="jazz",
            ))
        return events
