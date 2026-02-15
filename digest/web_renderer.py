"""Generate a static HTML page for the web dashboard."""
import os
from datetime import datetime
from math import ceil

from ranking.explainer import explain_event


def _format_price(event) -> str:
    if event.price_min is not None:
        if event.price_max and event.price_max != event.price_min:
            return f"${event.price_min:.0f}–${event.price_max:.0f}"
        return f"${event.price_min:.0f}"
    return "Price TBD"


def _format_time(event) -> str:
    dt = event.start_dt
    if hasattr(dt, "strftime"):
        return dt.strftime("%-I:%M %p")
    return str(dt)


def _format_day(event) -> str:
    dt = event.start_dt
    if hasattr(dt, "strftime"):
        return dt.strftime("%A, %b %-d")
    return ""


def _format_lead_time(event) -> str:
    """Return a human-readable lead time like 'in 3 weeks'."""
    dt = event.start_dt
    if not hasattr(dt, "date"):
        return ""
    days_out = (dt - datetime.now()).days
    if days_out < 14:
        return f"in {days_out} days"
    weeks = ceil(days_out / 7)
    return f"in {weeks} weeks"


def _render_event_card(event, scores, lead_time: str = "") -> str:
    explanation = explain_event(event)
    price = _format_price(event)
    time = _format_time(event)
    day = _format_day(event)

    ticket_html = ""
    if event.ticket_url:
        ticket_html = f'<a href="{event.ticket_url}" class="ticket-link">Tickets &rarr;</a>'

    lead_time_html = ""
    if lead_time:
        lead_time_html = f'<span class="event-lead-time">{lead_time}</span>'

    return f"""
      <article class="event-card">
        <div class="event-meta">{day} &middot; {time} &middot; {price}</div>
        <h3 class="event-title">{event.title}</h3>
        <div class="event-venue">{event.venue_name}{(' &middot; ' + event.neighborhood) if event.neighborhood else ''}</div>
        {lead_time_html}
        <p class="event-why">{explanation}</p>
        {ticket_html}
      </article>"""


def render_web(digest_data: dict, output_dir: str = None) -> str:
    """Generate index.html for the web dashboard."""
    output_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "docs")
    now = datetime.now()
    date_str = now.strftime("%A, %B %-d, %Y")
    time_str = now.strftime("%-I:%M %p")

    tonight_cards = ""
    for ev, scores in digest_data.get("tonight", []):
        tonight_cards += _render_event_card(ev, scores)

    week_cards = ""
    for ev, scores in digest_data.get("this_week", []):
        week_cards += _render_event_card(ev, scores)

    coming_up_cards = ""
    for ev, scores in digest_data.get("coming_up", []):
        coming_up_cards += _render_event_card(ev, scores, lead_time=_format_lead_time(ev))

    wildcard_card = ""
    wc = digest_data.get("wildcard")
    if wc:
        ev, scores = wc
        wildcard_card = _render_event_card(ev, scores)

    tonight_section = ""
    if tonight_cards:
        tonight_section = f"""
    <section>
      <h2 class="section-title">Tonight</h2>
      {tonight_cards}
    </section>"""

    week_section = ""
    if week_cards:
        week_section = f"""
    <section>
      <h2 class="section-title">This Week</h2>
      {week_cards}
    </section>"""

    coming_up_section = ""
    if coming_up_cards:
        coming_up_section = f"""
    <section>
      <h2 class="section-title">Coming Up</h2>
      {coming_up_cards}
    </section>"""

    wildcard_section = ""
    if wildcard_card:
        wildcard_section = f"""
    <section>
      <h2 class="section-title">Wildcard</h2>
      {wildcard_card}
    </section>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NYC Scout</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>NYC Scout</h1>
    <p class="subtitle">{date_str}</p>
    <p class="updated">Last updated {time_str}</p>
  </header>
  <main>
    {tonight_section}
    {week_section}
    {coming_up_section}
    {wildcard_section}
  </main>
  <footer>
    <p>NYC Concierge Scout &middot; Curated for you</p>
  </footer>
</body>
</html>"""

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w") as f:
        f.write(html)

    return output_path
