"""Generate short explanations for why an event is recommended."""
from __future__ import annotations

import os
import json
import logging

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# In-memory cache for explanations within a run
_explanation_cache: dict[str, str] = {}


def _get_venue_vibes(event, venues_config: dict) -> list[str]:
    """Get vibe tags for an event's venue."""
    for name, info in venues_config.items():
        if fuzz.ratio(event.venue_name.lower(), name.lower()) > 85:
            return info.get("vibe_tags", [])
    return []


def explain_template(event, prefs: dict, venues_config: dict) -> str:
    """Generate a template-based explanation (no LLM needed)."""
    vibes = _get_venue_vibes(event, venues_config)
    neighborhood = event.neighborhood or "NYC"

    # Build vibe description
    vibe_desc = ""
    if "intimate" in vibes:
        vibe_desc = "intimate"
    elif "elegant" in vibes:
        vibe_desc = "elegant"
    elif "legendary" in vibes:
        vibe_desc = "legendary"
    elif vibes:
        vibe_desc = vibes[0]
    else:
        vibe_desc = "cool"

    # Category label
    cat = event.category or "music"
    if cat == "jazz":
        cat_label = "jazz spot"
    elif cat == "exhibition":
        cat_label = "exhibition space"
    elif cat == "concert":
        cat_label = "music venue"
    else:
        cat_label = "venue"

    # Time description
    start_dt = event.start_dt
    if hasattr(start_dt, "strftime"):
        time_str = start_dt.strftime("%-I:%M %p")
        day_str = start_dt.strftime("%A")
    else:
        time_str = "tonight"
        day_str = ""

    # Price info
    price_str = ""
    if event.price_min is not None:
        price_str = f" (${event.price_min:.0f})"

    # Convenience note
    home = prefs.get("home_neighborhood", "").lower()
    if neighborhood.lower() == home:
        travel_note = "Right in your neighborhood."
    elif neighborhood.lower() in ("west village", "greenwich village", "flatiron"):
        travel_note = "Easy walk from home."
    else:
        travel_note = f"Over in {neighborhood}."

    # Social note
    social_note = ""
    if "date-friendly" in vibes:
        social_note = " Great date spot."
    elif "listening-room" in vibes:
        social_note = " Serious listening room — come for the music."

    # Artist info from entities
    artists = []
    try:
        for ent in event.entities:
            if ent.entity_type == "artist":
                artists.append(ent.entity_value)
    except Exception:
        pass

    artist_str = artists[0] if artists else event.title

    explanation = (
        f"{event.venue_name} is a {vibe_desc} {cat_label} in {neighborhood}. "
        f"{artist_str} at {time_str}{price_str}. "
        f"{travel_note}{social_note}"
    )
    return explanation.strip()


def explain_llm(event, prefs: dict, venues_config: dict) -> str | None:
    """Generate explanation via LLM API. Returns None if unavailable."""
    provider = os.environ.get("LLM_PROVIDER", "").lower()

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            vibes = _get_venue_vibes(event, venues_config)
            prompt = _build_prompt(event, prefs, vibes)
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"LLM explanation failed: {e}")
            return None

    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            vibes = _get_venue_vibes(event, venues_config)
            prompt = _build_prompt(event, prefs, vibes)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM explanation failed: {e}")
            return None

    return None


def _build_prompt(event, prefs: dict, vibes: list[str]) -> str:
    return (
        f"You're a concise NYC nightlife concierge. Write 1-2 sentences explaining "
        f"why someone who likes {', '.join(prefs.get('vibe_preferences', ['jazz']))} "
        f"would enjoy this event:\n\n"
        f"Event: {event.title}\n"
        f"Venue: {event.venue_name} ({', '.join(vibes)})\n"
        f"Neighborhood: {event.neighborhood}\n"
        f"Category: {event.category}\n"
        f"Time: {event.start_dt}\n"
        f"Price: ${event.price_min or '?'}\n\n"
        f"Keep it suave, knowledgeable, not touristy. Max 2 sentences."
    )


def match_reasons(event, scores: dict, prefs: dict = None, venues: dict = None) -> list[str]:
    """Return 1-2 short reason strings based on which scoring signals fired.

    Uses individual signal values from scores["signals"] to determine
    the most relevant reasons for recommending this event.
    """
    import yaml

    if prefs is None:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        with open(os.path.join(config_dir, "preferences.yaml")) as f:
            prefs = yaml.safe_load(f)
    if venues is None:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        with open(os.path.join(config_dir, "venues.yaml")) as f:
            venues = yaml.safe_load(f).get("venues", {})

    signals = scores.get("signals", {})
    reasons = []

    # Artist affinity (listening history signal returns 0-10, affinity is value/10)
    artist_affinity = signals.get("artist_affinity", 0)
    if artist_affinity > 0:
        pct = int(round(artist_affinity * 10))
        reasons.append(f"{pct}% Artist Match")

    # Venue reputation (0-10 scale from venue_boost)
    venue_rep = signals.get("venue_reputation", 0)
    if venue_rep > 5:
        reasons.append("Top venue for you")

    # Category weight (0-15 scale; high = category_weight >= 12, i.e. weight >= 0.8)
    cat_weight = signals.get("category_weight", 0)
    if cat_weight >= 12 and len(reasons) < 2:
        cat = event.category or "music"
        cat_label = cat.capitalize()
        reasons.append(f"{cat_label} affinity")

    # Home neighborhood
    home_match = signals.get("home_neighborhood", False)
    if home_match and len(reasons) < 2:
        reasons.append("In your neighborhood")

    # Fallback
    if not reasons:
        reasons.append("New discovery")

    return reasons[:2]


def explain_event(event, prefs: dict = None, venues_config: dict = None) -> str:
    """Generate explanation, trying LLM first then falling back to template."""
    import yaml

    if prefs is None:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        with open(os.path.join(config_dir, "preferences.yaml")) as f:
            prefs = yaml.safe_load(f)
    if venues_config is None:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        with open(os.path.join(config_dir, "venues.yaml")) as f:
            venues_config = yaml.safe_load(f).get("venues", {})

    # Check cache
    cache_key = f"{event.id}:{event.title}"
    if cache_key in _explanation_cache:
        return _explanation_cache[cache_key]

    # Try LLM
    explanation = explain_llm(event, prefs, venues_config)
    if not explanation:
        explanation = explain_template(event, prefs, venues_config)

    _explanation_cache[cache_key] = explanation
    return explanation
