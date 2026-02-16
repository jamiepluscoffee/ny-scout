"""Generate static HTML pages for the web dashboard — The Radar + The Full List."""
import json
import os
from datetime import datetime
from math import ceil

from ranking.explainer import match_reasons


def _format_price(event) -> str:
    if event.price_min is not None:
        if event.price_max and event.price_max != event.price_min:
            return f"${event.price_min:.0f}\u2013${event.price_max:.0f}"
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
        return dt.strftime("%a, %b %-d")
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


def _score_class(score: float) -> str:
    if score >= 65:
        return "high"
    if score >= 40:
        return "mid"
    return "low"


def _get_match_reasons(event, scores, prefs=None, venues=None) -> list[str]:
    """Get match reasons for an event, handling missing signals gracefully."""
    if "signals" not in scores:
        return ["New discovery"]
    return match_reasons(event, scores, prefs, venues)


def _render_event_card(event, scores, prefs=None, venues=None, lead_time: str = "") -> str:
    price = _format_price(event)
    time = _format_time(event)
    day = _format_day(event)
    total = round(scores.get("total", 0))
    sc = _score_class(total)
    reasons = _get_match_reasons(event, scores, prefs, venues)
    match_text = " + ".join(reasons)

    ticket_html = ""
    if event.ticket_url:
        ticket_html = (
            '<div class="event-actions">'
            f'<a href="{event.ticket_url}" class="ticket-btn" target="_blank" rel="noopener">'
            '\U0001f3ab Get Tickets</a></div>'
        )

    lead_time_html = ""
    if lead_time:
        lead_time_html = f'<span class="event-lead-time">{lead_time}</span>'

    return f"""
      <article class="event-card">
        <div class="event-info">
          <div class="event-title"><a href="{event.ticket_url or '#'}">{event.title}</a></div>
          <div class="event-meta">\U0001f4c5 {day} \u2022 {time}  \U0001f4cd {event.venue_name}{(', ' + event.neighborhood) if event.neighborhood else ''}    [{price}]</div>
          {lead_time_html}
          <div class="event-match"><span class="match-label">Match: </span><span class="match-text">{match_text}</span></div>
        </div>
        <div class="event-score">
          <div class="score-number {sc}">{total}</div>
          <div class="score-label">/100</div>
        </div>
        {ticket_html}
      </article>"""


def _sidebar_html(active_page: str) -> str:
    radar_cls = ' class="active"' if active_page == "radar" else ""
    list_cls = ' class="active"' if active_page == "list" else ""
    return f"""
  <nav class="sidebar">
    <div class="sidebar-brand">NYC SCOUT</div>
    <ul class="sidebar-nav">
      <li><a href="index.html"{radar_cls}>The Radar</a></li>
      <li><a href="list.html"{list_cls}>The Full List</a></li>
    </ul>
  </nav>"""


def _event_to_json(event, scores, prefs=None, venues=None) -> dict:
    """Convert an event to a JSON-serializable dict for client-side rendering."""
    reasons = _get_match_reasons(event, scores, prefs, venues)
    artists = []
    try:
        for ent in event.entities:
            if ent.entity_type == "artist":
                artists.append(ent.entity_value)
    except Exception:
        pass

    return {
        "title": event.title,
        "venue": event.venue_name,
        "neighborhood": event.neighborhood or "",
        "artists": ", ".join(artists),
        "day": _format_day(event),
        "time": _format_time(event),
        "start_dt": event.start_dt.isoformat() if hasattr(event.start_dt, "isoformat") else str(event.start_dt),
        "price": _format_price(event),
        "score": round(scores.get("total", 0), 1),
        "match_reasons": reasons,
        "ticket_url": event.ticket_url or "",
    }


def render_web(digest_data: dict, output_dir: str = None, prefs: dict = None, venues: dict = None) -> str:
    """Generate index.html (The Radar) for the web dashboard."""
    output_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "docs")
    now = datetime.now()
    date_str = now.strftime("%A, %B %-d, %Y")
    time_str = now.strftime("%-I:%M %p")

    tonight_cards = ""
    for ev, scores in digest_data.get("tonight", []):
        tonight_cards += _render_event_card(ev, scores, prefs, venues)

    week_cards = ""
    for ev, scores in digest_data.get("this_week", []):
        week_cards += _render_event_card(ev, scores, prefs, venues)

    coming_up_cards = ""
    for ev, scores in digest_data.get("coming_up", []):
        coming_up_cards += _render_event_card(ev, scores, prefs, venues, lead_time=_format_lead_time(ev))

    wildcard_card = ""
    wc = digest_data.get("wildcard")
    if wc:
        ev, scores = wc
        wildcard_card = _render_event_card(ev, scores, prefs, venues)

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

    sidebar = _sidebar_html("radar")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NYC Scout \u2014 The Radar</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {sidebar}
  <div class="main-content">
    <header>
      <h1>THE DIGEST</h1>
      <p class="subtitle">Curated for Jamie</p>
      <p class="updated">Last updated {time_str} \u2022 {date_str}</p>
    </header>
    <main>
      {tonight_section}
      {week_section}
      {coming_up_section}
      {wildcard_section}
    </main>
    <footer>
      <p>NYC Scout \u00b7 Curated for Jamie</p>
    </footer>
  </div>
</body>
</html>"""

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def render_full_list(full_list_data: list[tuple], output_dir: str = None, prefs: dict = None, venues: dict = None) -> str:
    """Generate list.html (The Full List) with embedded JSON for client-side interactivity."""
    output_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "docs")
    now = datetime.now()
    time_str = now.strftime("%-I:%M %p")
    date_str = now.strftime("%A, %B %-d, %Y")

    # Build JSON data for all events
    events_json = []
    for ev, scores in full_list_data:
        # Patch entities if needed
        try:
            entities = ev._prefetched_entities if hasattr(ev, "_prefetched_entities") else list(ev.entities)
            original = ev.entities
            ev.entities = entities
            events_json.append(_event_to_json(ev, scores, prefs, venues))
            ev.entities = original
        except Exception:
            events_json.append(_event_to_json(ev, scores, prefs, venues))

    json_str = json.dumps(events_json, ensure_ascii=False)
    sidebar = _sidebar_html("list")
    total_count = len(events_json)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NYC Scout \u2014 The Full List</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {sidebar}
  <div class="main-content">
    <header>
      <h1>THE FULL LIST</h1>
      <p class="subtitle">{total_count} scored events</p>
      <p class="updated">Last updated {time_str} \u2022 {date_str}</p>
    </header>
    <main>
      <div class="list-controls">
        <input type="text" id="search-input" class="search-input" placeholder="Search by title, artist, or venue\u2026">
        <select id="sort-select" class="sort-select">
          <option value="score">Sort: Taste Score</option>
          <option value="date">Sort: Date</option>
        </select>
        <div id="list-status" class="list-status"></div>
      </div>
      <div id="event-list"></div>
      <button id="load-more-btn" class="load-more-btn">Load More</button>
    </main>
    <footer>
      <p>NYC Scout \u00b7 Curated for Jamie</p>
    </footer>
  </div>
  <script id="event-data" type="application/json">{json_str}</script>
  <script src="app.js"></script>
</body>
</html>"""

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "list.html")
    with open(output_path, "w") as f:
        f.write(html)

    return output_path
