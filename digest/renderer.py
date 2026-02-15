"""Render digest as HTML email body."""
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
        return dt.strftime("%a %b %-d")
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


def _render_event_html(event, scores, index: int, lead_time: str = "") -> str:
    explanation = explain_event(event)
    price = _format_price(event)
    time = _format_time(event)
    day = _format_day(event)

    ticket_link = ""
    if event.ticket_url:
        ticket_link = f' · <a href="{event.ticket_url}" style="color: #b8860b;">Tickets</a>'

    lead_time_html = ""
    if lead_time:
        lead_time_html = f'<div style="font-size: 11px; color: #8a7e6b; margin-bottom: 4px;">{lead_time}</div>'

    return f"""
    <tr>
      <td style="padding: 16px 0; border-bottom: 1px solid #e8e0d0;">
        <div style="font-size: 11px; color: #8a7e6b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">
          {day} · {time} · {price}{ticket_link}
        </div>
        <div style="font-size: 17px; font-weight: 600; color: #2c2416; margin-bottom: 6px;">
          {index}. {event.title}
        </div>
        <div style="font-size: 13px; color: #6b5e4b; margin-bottom: 4px;">
          {event.venue_name}{(' · ' + event.neighborhood) if event.neighborhood else ''}
        </div>
        {lead_time_html}
        <div style="font-size: 14px; color: #4a4132; line-height: 1.5; font-style: italic;">
          {explanation}
        </div>
      </td>
    </tr>"""


def render_html(digest_data: dict) -> str:
    """Render the full digest as an HTML email."""
    now = datetime.now()
    date_str = now.strftime("%A, %B %-d")

    tonight_rows = ""
    for i, (ev, scores) in enumerate(digest_data.get("tonight", []), 1):
        tonight_rows += _render_event_html(ev, scores, i)

    week_rows = ""
    for i, (ev, scores) in enumerate(digest_data.get("this_week", []), 1):
        week_rows += _render_event_html(ev, scores, i)

    coming_up_rows = ""
    for i, (ev, scores) in enumerate(digest_data.get("coming_up", []), 1):
        coming_up_rows += _render_event_html(ev, scores, i, lead_time=_format_lead_time(ev))

    wildcard_row = ""
    wc = digest_data.get("wildcard")
    if wc:
        ev, scores = wc
        wildcard_row = _render_event_html(ev, scores, 1)

    tonight_section = ""
    if tonight_rows:
        tonight_section = f"""
        <tr>
          <td style="padding: 24px 0 8px;">
            <h2 style="font-size: 14px; text-transform: uppercase; letter-spacing: 2px; color: #b8860b; margin: 0; font-weight: 600;">Tonight</h2>
          </td>
        </tr>
        {tonight_rows}"""

    week_section = ""
    if week_rows:
        week_section = f"""
        <tr>
          <td style="padding: 24px 0 8px;">
            <h2 style="font-size: 14px; text-transform: uppercase; letter-spacing: 2px; color: #b8860b; margin: 0; font-weight: 600;">This Week</h2>
          </td>
        </tr>
        {week_rows}"""

    coming_up_section = ""
    if coming_up_rows:
        coming_up_section = f"""
        <tr>
          <td style="padding: 24px 0 8px;">
            <h2 style="font-size: 14px; text-transform: uppercase; letter-spacing: 2px; color: #b8860b; margin: 0; font-weight: 600;">Coming Up</h2>
            <div style="font-size: 12px; color: #8a7e6b; margin-top: 4px;">Worth booking now</div>
          </td>
        </tr>
        {coming_up_rows}"""

    wildcard_section = ""
    if wildcard_row:
        wildcard_section = f"""
        <tr>
          <td style="padding: 24px 0 8px;">
            <h2 style="font-size: 14px; text-transform: uppercase; letter-spacing: 2px; color: #b8860b; margin: 0; font-weight: 600;">Wildcard</h2>
          </td>
        </tr>
        {wildcard_row}"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin: 0; padding: 0; background-color: #f5f0e8; font-family: Georgia, 'Times New Roman', serif;">
  <table role="presentation" width="100%" style="max-width: 600px; margin: 0 auto; background: #fffdf7; border-radius: 4px; overflow: hidden;">
    <tr>
      <td style="padding: 32px 24px 16px; text-align: center; border-bottom: 2px solid #e8e0d0;">
        <h1 style="font-size: 22px; color: #2c2416; margin: 0 0 4px; font-weight: 400; letter-spacing: 1px;">NYC Scout</h1>
        <div style="font-size: 13px; color: #8a7e6b;">{date_str}</div>
      </td>
    </tr>
    <tr>
      <td style="padding: 0 24px 32px;">
        <table role="presentation" width="100%">
          {tonight_section}
          {week_section}
          {coming_up_section}
          {wildcard_section}
        </table>
      </td>
    </tr>
    <tr>
      <td style="padding: 16px 24px; text-align: center; border-top: 2px solid #e8e0d0; font-size: 11px; color: #8a7e6b;">
        NYC Concierge Scout · Curated for you
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_subject(digest_data: dict) -> str:
    """Generate email subject line."""
    now = datetime.now()
    date_str = now.strftime("%a %b %-d")
    tonight_count = len(digest_data.get("tonight", []))
    parts = []
    if tonight_count:
        parts.append("Tonight")
    parts.append("This Week")
    return f"NYC Scout — {' + '.join(parts)} ({date_str})"
