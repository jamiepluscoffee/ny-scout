"""Generate static HTML pages for the web dashboard — The Radar + The Full List."""
import json
import os
from datetime import datetime
from html import escape
from math import ceil

from ranking.explainer import match_reasons

# SVG icons (from Lucide, matching the Figma design)
_ICON_DISC = '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>'
_ICON_RADAR = '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/></svg>'
_ICON_CAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>'
_ICON_PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>'
_ICON_TICKET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/></svg>'
_ICON_SEARCH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>'
_ICON_SORT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/></svg>'
_ICON_ARROWS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/></svg>'


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
    dt = event.start_dt
    if not hasattr(dt, "date"):
        return ""
    days_out = (dt - datetime.now()).days
    if days_out < 14:
        return f"in {days_out} days"
    weeks = ceil(days_out / 7)
    return f"in {weeks} weeks"


def _get_match_reasons(event, scores, prefs=None, venues=None) -> list[str]:
    if "signals" not in scores:
        return ["New discovery"]
    return match_reasons(event, scores, prefs, venues)


def _render_event_card(event, scores, prefs=None, venues=None, lead_time: str = "") -> str:
    price = _format_price(event)
    time = _format_time(event)
    day = _format_day(event)
    total = round(scores.get("total", 0))
    reasons = _get_match_reasons(event, scores, prefs, venues)
    match_text = " + ".join(reasons)

    title = escape(event.title)
    venue = escape(event.venue_name)
    hood = escape(event.neighborhood) if event.neighborhood else ""
    venue_display = f"{venue}, {hood}" if hood else venue

    ticket_html = ""
    if event.ticket_url:
        ticket_html = (
            f'<a href="{escape(event.ticket_url)}" class="ticket-btn" target="_blank" rel="noopener">'
            f'{_ICON_TICKET} Get Tickets</a>'
        )

    lead_time_html = ""
    if lead_time:
        lead_time_html = f'<div class="event-lead-time">{lead_time}</div>'

    return f"""
      <article class="event-card">
        <div class="event-card-body">
          <div class="event-card-info">
            <div class="event-artist">{title}</div>
            <div class="event-meta">
              <span class="event-meta-item">{_ICON_CAL} <span>{day} &bull; {time}</span></span>
              <span class="event-meta-item">{_ICON_PIN} <span class="venue-text">{venue_display}</span></span>
            </div>
            {lead_time_html}
          </div>
          <div class="event-card-right">
            <div class="event-score">
              <span class="score-number">{total}</span>
              <span class="score-label">/100</span>
            </div>
            <div class="event-price">{price}</div>
          </div>
        </div>
        <div class="event-card-footer">
          <div class="event-footer-left">
            <div class="event-match">
              <span class="match-label">Match:</span> {match_text}
            </div>
          </div>
          {ticket_html}
        </div>
      </article>"""


def _sidebar_html(active_page: str) -> str:
    radar_cls = ' class="active"' if active_page == "radar" else ""
    list_cls = ' class="active"' if active_page == "list" else ""
    return f"""
  <nav class="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-brand-icon">NY</div>
      <span class="sidebar-brand-text">NY Scout</span>
    </div>
    <ul class="sidebar-nav">
      <li><a href="index.html"{radar_cls}>{_ICON_DISC} The Radar</a></li>
      <li><a href="list.html"{list_cls}>{_ICON_RADAR} The Full List</a></li>
    </ul>
  </nav>"""


def _event_to_json(event, scores, prefs=None, venues=None) -> dict:
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

    sidebar = _sidebar_html("radar")

    # Build sections with category labels
    sections_html = ""

    tonight = digest_data.get("tonight", [])
    if tonight:
        cards = ""
        for ev, scores in tonight:
            cards += _render_event_card(ev, scores, prefs, venues)
        sections_html += f'<div class="section-label">Tonight</div>\n{cards}'

    week = digest_data.get("this_week", [])
    if week:
        cards = ""
        for ev, scores in week:
            cards += _render_event_card(ev, scores, prefs, venues)
        sections_html += f'<div class="section-label">This Week</div>\n{cards}'

    coming = digest_data.get("coming_up", [])
    if coming:
        cards = ""
        for ev, scores in coming:
            cards += _render_event_card(ev, scores, prefs, venues, lead_time=_format_lead_time(ev))
        sections_html += f'<div class="section-label">Coming Up</div>\n{cards}'

    wc = digest_data.get("wildcard")
    if wc:
        ev, scores = wc
        card = _render_event_card(ev, scores, prefs, venues)
        sections_html += f'<div class="section-label">Wildcard</div>\n{card}'

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
    <h1 class="page-title">The Radar</h1>

    <div class="digest-header">
      <span class="digest-title">The Digest</span>
      <span class="digest-subtitle">Curated for <strong>Jamie</strong></span>
    </div>

    {sections_html}

    <footer>
      <p>NYC Scout &middot; Curated for Jamie</p>
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

    # Build JSON data for all events
    events_json = []
    for ev, scores in full_list_data:
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
    <h1 class="page-title">The Full List</h1>

    <div class="list-controls">
      <div class="list-controls-row">
        <div class="search-wrapper">
          {_ICON_SEARCH}
          <input type="text" id="search-input" class="search-input" placeholder="Search events, artists, venues...">
        </div>
        <div class="control-chips">
          <button id="sort-score" class="control-chip active" data-sort="score">{_ICON_SORT} Sort: Taste Score</button>
          <button id="sort-date" class="control-chip" data-sort="date">{_ICON_SORT} Sort: Date</button>
        </div>
      </div>
    </div>

    <div id="event-list"></div>

    <div id="load-more-area" class="load-more-area">
      <div class="load-more-inner">
        <div class="load-more-icon">{_ICON_ARROWS}</div>
        <div>
          <div class="load-more-text">Load More Events</div>
          <div id="list-status" class="load-more-count">Showing 0 of {total_count} matches</div>
        </div>
      </div>
    </div>

    <footer>
      <p>NYC Scout &middot; Curated for Jamie</p>
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
